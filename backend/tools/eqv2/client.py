"""EqV2 31M 机器学习势函数服务的 HTTP 客户端。

服务契约见 doc/EQV2_AGENT_API_GUIDE.md 与 doc/EQV2_SERVER_IMPLEMENTATION.md。

═══════════════════════════════════════════════════════════════════════
为什么这个客户端比"直接 requests.post"复杂这么多
═══════════════════════════════════════════════════════════════════════

服务端是 **2 vCPU / 3.5 GB、uvicorn 单 worker、单任务锁**，前面还挂着 Nginx
做每 IP 限流。实测：连发 20 次请求有 16 次被 Nginx 打成 503，放慢到
1 请求 / 10s 后 30/30 全成功。

**唯一有效的对策是本地串行 + 退避重试**，而不是加超时或加并发。所以本模块：

  1. 用一把模块级锁把所有出网请求串起来（`_HTTP_LOCK`）。
  2. 按状态码分流重试：409 等 15s、429 等 30s、5xx 指数退避、401/422 直接失败。

第二点上最容易写错的是 **401 与 422 绝不能重试** —— 它们不是暂时的，重试
只会把 4 次配额白白烧掉，还会让用户多等半分钟才看到"Key 错了"。

═══════════════════════════════════════════════════════════════════════
relax 提交为什么单独走一条路径
═══════════════════════════════════════════════════════════════════════

文档 §7 明确要求：**不要在 HTTP 超时后盲目重复提交优化**，因为无法判断任务
是否已经创建。所以：

  - 收到**明确**的 409/429/5xx → 确定没建任务 → 可以重试；
  - 连接错误 / 超时 → **不确定** → 抛 `EqV2SubmitUncertain`，绝不重发。

前者是"服务拒绝了我"，后者是"我不知道发生了什么"。把这两者混为一谈，就是
重复提交与算力浪费的来源。
"""

import random
import threading
import time

import requests

from app.utils.logger import logger
from config.settings import settings


# ─────────────────────────────────────────────────────────────
# 异常
# ─────────────────────────────────────────────────────────────

class EqV2Error(Exception):
    """EqV2 调用失败的基类。"""


class EqV2AuthError(EqV2Error):
    """401 —— Key 缺失或错误。**不重试**，重试不会让 Key 变对。"""


class EqV2InputError(EqV2Error):
    """422 —— XYZ 或参数不合法。**不重试**，要改的是输入。"""


class EqV2SubmitUncertain(EqV2Error):
    """提交 relax 时连接中断/超时，无法判断作业是否已创建。

    调用方**不得**重发，应先按已有信息排查（文档 §7 末段）。
    """


# ─────────────────────────────────────────────────────────────
# 常量
# ─────────────────────────────────────────────────────────────

# 服务端单任务锁 → 本地也要串行。RLock 而非 Lock：防止将来有人在
# 持锁方法内部再调另一个持锁方法时死锁。
_HTTP_LOCK = threading.RLock()

# 409 = 模型正忙，文档建议等 10~20s
_BUSY_SLEEP = 15.0
# 429 = 优化队列已满 / 调用过快，文档建议至少 30s
_RATE_LIMIT_SLEEP = 30.0
# 5xx 指数退避起点（1 → 2 → 4 → 8 ...）
_BACKOFF_BASE = 1.0
# 提交 relax 是入队操作，本身很快；给它一个更短的上限，
# 免得一个卡住的连接把工具调用挂满整个 EQV2_TIMEOUT
_SUBMIT_TIMEOUT_CAP = 60.0

_TERMINAL_STATUSES = {"completed", "failed"}


def _redact(text: str, secret: str) -> str:
    """把 Key 从任意文本里抹掉。

    红线：Key 不得进日志、异常消息、工具返回值。服务端理论上不会回显它，
    但"理论上"不足以让我们把它原样写进 error.log。
    """
    if secret and secret in text:
        return text.replace(secret, "***REDACTED***")
    return text


def _body_excerpt(resp) -> str:
    """截取响应体前 200 字用于报错 —— 完整 body 可能是巨长的 422 detail。"""
    try:
        raw = resp.text or ""
    except Exception:
        return "<无法读取响应体>"
    raw = raw.strip().replace("\n", " ")
    return raw[:200] + ("..." if len(raw) > 200 else "")


class EqV2Client:
    """EqV2 服务的同步客户端。线程安全（但会串行化，见模块 docstring）。"""

    def __init__(self, base_url: str = None, api_key: str = None,
                 timeout: float = None, max_retries: int = None):
        self.base_url = (base_url or settings.EQV2_API_BASE_URL).rstrip("/")
        self._api_key = api_key if api_key is not None else settings.EQV2_API_KEY
        self.timeout = timeout if timeout is not None else settings.EQV2_TIMEOUT
        self.max_retries = (max_retries if max_retries is not None
                            else settings.EQV2_MAX_RETRIES)
        self._session = requests.Session()
        # ⚠️ 只打 base_url，绝不打 Key
        logger.bind(component="eqv2").debug(
            "[eqv2] client init | base_url={} | timeout={}s | max_retries={} | key={}",
            self.base_url, self.timeout, self.max_retries,
            "已配置" if self._api_key else "缺失",
        )

    # ─── 内部：带重试的请求 ───────────────────────────────
    def _request(self, method: str, path: str, *, json_body: dict = None,
                 timeout: float = None, idempotent: bool = True):
        """发一个请求并按策略重试。

        idempotent=False（仅 relax 提交）时，连接错误/超时直接抛
        EqV2SubmitUncertain 而不重试 —— 见模块 docstring。
        """
        url = f"{self.base_url}{path}"
        timeout = timeout or self.timeout
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        last_desc = None
        for attempt in range(self.max_retries + 1):
            t0 = time.perf_counter()
            with _HTTP_LOCK:
                try:
                    resp = self._session.request(
                        method, url, json=json_body, headers=headers, timeout=timeout
                    )
                except (requests.ConnectionError, requests.Timeout) as e:
                    elapsed = (time.perf_counter() - t0) * 1000
                    desc = f"{type(e).__name__}: {_redact(str(e), self._api_key)}"
                    if not idempotent:
                        # 不知道服务端收没收到 —— 绝不重发
                        logger.bind(component="eqv2").warning(
                            "[eqv2] 提交结果不确定 | {} {} | elapsed={:.0f}ms | {}",
                            method, path, elapsed, desc,
                        )
                        raise EqV2SubmitUncertain(
                            f"提交时连接中断（{desc}）。无法判断作业是否已创建，"
                            f"为避免重复提交已停止重试。"
                        ) from e
                    logger.bind(component="eqv2").warning(
                        "[eqv2] 网络错误 attempt={}/{} | {} {} | elapsed={:.0f}ms | {}",
                        attempt + 1, self.max_retries + 1, method, path, elapsed, desc,
                    )
                    last_desc = desc
                    if attempt >= self.max_retries:
                        break
                    time.sleep(self._backoff(attempt))
                    continue

            status = resp.status_code
            elapsed = (time.perf_counter() - t0) * 1000

            # ── 成功 ──
            if status in (200, 202):
                logger.bind(component="eqv2").info(
                    "[eqv2] {} {} | status={} | attempt={} | elapsed={:.0f}ms",
                    method, path, status, attempt + 1, elapsed,
                )
                return resp

            # ── 不重试的失败 ──
            if status == 401:
                logger.bind(component="eqv2").error(
                    "[eqv2] 鉴权失败 | {} {} | status=401", method, path,
                )
                raise EqV2AuthError(
                    "EqV2 服务拒绝了该 API Key（401 invalid API key）。"
                    "请检查 .env 中的 EQV2_API_KEY —— 这是配置问题，重试无效。"
                )
            if status == 422:
                detail = _redact(_body_excerpt(resp), self._api_key)
                logger.bind(component="eqv2").warning(
                    "[eqv2] 输入被拒 | {} {} | status=422 | {}",
                    method, path, detail,
                )
                raise EqV2InputError(f"EqV2 拒绝了输入（422）: {detail}")
            if status == 404:
                # 实测：未知 job_id 返回 404 {"detail":"job not found"}。
                # 也覆盖 base_url 配错导致所有路径都 404 的情况。
                logger.bind(component="eqv2").warning(
                    "[eqv2] 404 | {} {} | {}", method, path, _body_excerpt(resp),
                )
                raise EqV2Error(
                    f"EqV2 返回 404（{path}）：作业不存在，或接口路径不对。"
                    f"请检查 job_id 与 EQV2_API_BASE_URL。"
                )

            # ── 可重试的失败 ──
            if status == 409:
                sleep_s = _BUSY_SLEEP
                reason = "模型正忙（409）"
            elif status == 429:
                sleep_s = _RATE_LIMIT_SLEEP
                reason = "队列已满/调用过快（429）"
            elif status in (500, 502, 503, 504):
                sleep_s = self._backoff(attempt)
                reason = f"服务端临时错误（{status}）"
            else:
                # 其他 4xx：未知语义，重试无意义
                detail = _redact(_body_excerpt(resp), self._api_key)
                logger.bind(component="eqv2").error(
                    "[eqv2] 未知失败 | {} {} | status={} | {}",
                    method, path, status, detail,
                )
                raise EqV2Error(f"EqV2 返回 {status}: {detail}")

            last_desc = f"{reason} status={status}"
            if attempt >= self.max_retries:
                logger.bind(component="eqv2").error(
                    "[eqv2] 重试耗尽 | {} {} | {} | attempts={}",
                    method, path, last_desc, attempt + 1,
                )
                break

            logger.bind(component="eqv2").warning(
                "[eqv2] {} 退避 {:.1f}s 后重试 | {} {} | attempt={}/{}",
                reason, sleep_s, method, path, attempt + 1, self.max_retries + 1,
            )
            time.sleep(sleep_s)

        raise EqV2Error(
            f"EqV2 请求失败，已重试 {self.max_retries} 次。最后一次原因: {last_desc}。"
            f"该服务为单任务执行且有限流，请稍后重试，不要并发提交。"
        )

    @staticmethod
    def _backoff(attempt: int) -> float:
        """指数退避 + 抖动。抖动是为了避免多个调用方同步重试再次撞上限流。"""
        return _BACKOFF_BASE * (2 ** attempt) + random.uniform(0, 0.5)

    # ─── 只读接口 ─────────────────────────────────────────
    def health(self) -> dict:
        """服务存活 + 模型加载状态。**无需 Key**。"""
        return self._request("GET", "/health").json()

    def models(self) -> dict:
        """模型名、设备与限制。需要 Key。"""
        return self._request("GET", "/v1/models").json()

    def ensure_reachable(self) -> dict:
        """预检：服务活着、Key 有效、模型已加载。失败抛 EqV2Error 系列。

        工具入口先调它，可以把"Key 没配""服务挂了"与"计算失败"区分开。
        """
        info = self.health()
        if not info.get("model_loaded"):
            raise EqV2Error(f"EqV2 服务在线但模型尚未加载: {info}")
        self.models()          # 顺带验 Key —— 缺 Key/错 Key 在这里抛 EqV2AuthError
        return info

    # ─── 单点计算（同步） ─────────────────────────────────
    def predict(self, xyz: str) -> dict:
        """单点能量 + 原子力。同步，实测约 0.2s。返回 data 字段。"""
        resp = self._request("POST", "/v1/predict", json_body={"xyz": xyz})
        payload = resp.json()
        if not payload.get("success"):
            raise EqV2Error(f"EqV2 predict 未成功: {_redact(str(payload), self._api_key)}")
        return payload["data"]

    # ─── 结构优化（异步） ─────────────────────────────────
    def submit_relax(self, xyz: str, fmax: float = 0.05,
                     max_steps: int = 200) -> str:
        """提交优化作业，返回 job_id。"""
        timeout = min(self.timeout, _SUBMIT_TIMEOUT_CAP)
        resp = self._request(
            "POST", "/v1/relax",
            json_body={"xyz": xyz, "fmax": fmax, "max_steps": max_steps},
            timeout=timeout,
            idempotent=False,          # ← 关键：超时不重发
        )
        payload = resp.json()
        job_id = payload.get("job_id")
        if not job_id:
            raise EqV2Error(f"EqV2 relax 未返回 job_id: {payload}")
        logger.bind(component="eqv2").info(
            "[eqv2] relax 已提交 | job_id={} | fmax={} | max_steps={}",
            job_id, fmax, max_steps,
        )
        return job_id

    def get_job(self, job_id: str) -> dict:
        """查询作业状态。终态为 completed / failed。"""
        return self._request("GET", f"/v1/jobs/{job_id}").json()

    def wait_for_job(self, job_id: str, on_progress=None,
                     poll_interval: float = None,
                     total_timeout: float = None) -> dict:
        """轮询到终态。

        ⚠️ 轮询期间**不持锁** —— 每轮 get_job 各自加锁。否则一次 30 分钟的
           优化会把整个客户端锁死，连 health 都查不了。
        """
        poll_interval = poll_interval or settings.EQV2_POLL_INTERVAL
        total_timeout = total_timeout or settings.EQV2_RELAX_TIMEOUT
        deadline = time.time() + total_timeout

        last_status = None
        while True:
            job = self.get_job(job_id)
            status = job.get("status")

            if status != last_status:
                logger.bind(component="eqv2").info(
                    "[eqv2] job={} status={} -> {}", job_id, last_status, status,
                )
                last_status = status
            if on_progress is not None:
                on_progress(job)

            if status in _TERMINAL_STATUSES:
                return job
            if status not in ("queued", "running"):
                # 服务端新增了状态？当作失败上报，不要静默死循环
                raise EqV2Error(f"EqV2 返回了未知作业状态 '{status}': {job}")
            if time.time() > deadline:
                raise EqV2Error(
                    f"EqV2 优化作业 {job_id} 超过 {total_timeout:.0f}s 仍未结束"
                    f"（当前 {status}）。作业可能仍在服务端运行，可稍后重新查询。"
                )
            time.sleep(poll_interval)

    def get_structure(self, job_id: str) -> str:
        """下载优化后的扩展 XYZ 文本（含 energy 与 forces 列）。"""
        return self._request("GET", f"/v1/jobs/{job_id}/structure").text


# ─────────────────────────────────────────────────────────────
# 惰性单例
# ─────────────────────────────────────────────────────────────
_client: EqV2Client | None = None
_client_lock = threading.Lock()


def get_client() -> EqV2Client:
    """进程内复用同一个 client（复用连接池）。

    ⚠️ 惰性构造而非模块级实例：Key 缺失要在**调用时**报错并给出可读提示，
       而不是让 import 期就炸掉整个工具模块的加载。
    """
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                _client = EqV2Client()
    return _client
