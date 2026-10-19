"""项目统一日志模块（loguru 驱动）。

用法：
    from app.utils.logger import logger, mask_sensitive, set_request_id

规范：
    - 一切日志走本模块的 logger，禁止 print / 裸标准库 logging
    - 状态变更打 info，失败分支 raise 前打 warning，异常块打 exception
    - 记录入参先过 mask_sensitive 脱敏
    - 需要附加字段用 logger.bind(task_id=...)，**不要**用 logger.contextualize()

⚠️ 为什么禁止 logger.contextualize()：
    SSE 生成器由 Starlette 抛到线程池执行，anyio 每次 next() 都 copy_context()，
    生成器体内对 ContextVar 的 set() 在下一个 yield 后即失效。
    contextualize 内部就是 ContextVar，同样会静默失效 —— 日志字段会莫名变成默认值。
    而 logger.bind() 是每次调用显式携带，不受影响。

日志目录：项目根 logs/（可用 LOG_DIR 环境变量覆盖）。
    - 本地开发：<仓库根>/logs/，cd 到哪都不影响（基于 __file__ 推导）
    - 容器部署：Dockerfile 的 WORKDIR=/app 下不存在仓库根，会回退到 backend/ 自身，
      此时建议用 LOG_DIR=/app/logs 显式指定
"""
import logging
import os
import re
import sys
from contextvars import ContextVar

# ─────────────────────────────────────────────────────────────
# loguru 引入 + 缺失时的降级替身
#
# 为什么要 shim：agent/state.py 等核心链路会 import 本模块，日志依赖一旦缺失
# 会让整个 Agent 链路 import 失败 —— 故障等级从「没有日志」升级成「服务起不来」。
# shim 保证「可观测性改造绝不会让系统变不可用」。
# ─────────────────────────────────────────────────────────────
try:
    from loguru import logger  # type: ignore
    _HAS_LOGURU = True
except ModuleNotFoundError:  # pragma: no cover - 仅依赖缺失时走到
    _HAS_LOGURU = False

    class _ShimLogger:
        """loguru 缺失时的最小替身：支持 loguru 风格的 {} 格式化与 bind/opt 链式调用。

        只保证「有日志、不崩」，不保证 request_id 注入、按日切分与彩色输出。
        """

        _LEVELS = {
            "debug": logging.DEBUG, "info": logging.INFO,
            "warning": logging.WARNING, "error": logging.ERROR,
            "critical": logging.CRITICAL,
        }

        def __init__(self, name: str = "app", extra: dict | None = None):
            self._name = name
            self._extra = extra or {}
            self._exc = False

        def bind(self, **kw):
            return _ShimLogger(self._name, {**self._extra, **kw})

        def opt(self, exception=None, depth: int = 0, **kw):
            self._exc = bool(exception)
            return self

        def _emit(self, level_name: str, msg, *args):
            lvl = self._LEVELS[level_name]
            lg = logging.getLogger(self._name)
            if not lg.isEnabledFor(lvl):
                return
            try:
                text = msg.format(*args) if args else str(msg)
            except Exception:
                text = f"{msg} {args}"
            if self._extra:
                suffix = " ".join(f"{k}={v}" for k, v in self._extra.items())
                text = f"{text} | {suffix}"
            lg.log(lvl, text, exc_info=self._exc and lvl >= logging.ERROR)
            self._exc = False

        def debug(self, msg, *a): self._emit("debug", msg, *a)
        def info(self, msg, *a): self._emit("info", msg, *a)
        def warning(self, msg, *a): self._emit("warning", msg, *a)
        def error(self, msg, *a): self._emit("error", msg, *a)
        def critical(self, msg, *a): self._emit("critical", msg, *a)

        def exception(self, msg, *a):
            self._exc = True
            self._emit("error", msg, *a)

        # setup_logger() 会调用的 no-op 接口
        def remove(self, *a, **k): return None
        def add(self, *a, **k): return None
        def configure(self, *a, **k): return None
        def level(self, *a, **k): return None

    logger = _ShimLogger()  # type: ignore

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(message)s",
    )
    print(
        "[logger] [WARN] 未安装 loguru，已退化为标准库 logging（无 request_id / 无按日切分）。"
        "请执行 `python -m pip install loguru` 启用完整日志。",
        file=sys.stderr,
    )


# ─────────────────────────────────────────────────────────────
# 请求上下文（中间件写入，patcher 读取并注入每条日志）
# ─────────────────────────────────────────────────────────────
_request_id: ContextVar[str] = ContextVar("request_id", default="-")
_user_id: ContextVar[str] = ContextVar("user_id", default="default_user")

# 与 logger.configure(extra=...) 里的默认值保持一致，供 patcher 判断「是否已被显式 bind」
_DEFAULT_REQUEST_ID = "-"
_DEFAULT_USER_ID = "-"

# 敏感字段名 / 敏感键值对（脱敏用）
_SENSITIVE_KEY = re.compile(
    r"(password|passwd|pwd|token|api_key|apikey|authorization|secret|credential|access_key|secret_key)",
    re.IGNORECASE,
)
_SENSITIVE_PAIR = re.compile(
    r"(?i)(password|passwd|pwd|token|api_key|apikey|authorization|secret|credential|access_key|secret_key)"
    r"\s*[=:]\s*([^&\s,;]+)"
)


def set_request_id(rid: str) -> None:
    """中间件每请求调用一次，写入当前请求的 request_id。

    ⚠️ 必须在**中间件**或**端点体**调用，不能在 SSE 生成器体内 ——
       生成器跑在线程池，体内设的 ContextVar 在下一个 yield 后即失效。
    """
    _request_id.set(rid)


def get_request_id() -> str:
    return _request_id.get()


def set_user_id(uid: str) -> None:
    _user_id.set(uid)


def get_user_id() -> str:
    return _user_id.get()


def mask_sensitive(data, _depth: int = 0):
    """递归脱敏：dict 敏感 key 的值 → '***'；字符串按正则替换敏感键值对。"""
    if _depth > 10:
        return data
    if isinstance(data, dict):
        return {
            k: ("***" if _SENSITIVE_KEY.search(str(k)) else mask_sensitive(v, _depth + 1))
            for k, v in data.items()
        }
    if isinstance(data, (list, tuple)):
        return [mask_sensitive(v, _depth + 1) for v in data]
    if isinstance(data, str):
        return _SENSITIVE_PAIR.sub(lambda m: f"{m.group(1)}=***", data)
    return data


def _patch_record(record) -> None:
    """loguru patcher：每条日志注入当前 request_id / user_id（来自 contextvar）。

    ⚠️ 只在「没有被 logger.bind() 显式覆盖」时才注入 —— 判据是 extra 里仍是配置的默认值。

    为什么需要这层判断：SSE 生成器被**客户端中途断连**触发 close() 时，生成器的 finally
    会跑在一个已脱离请求上下文的作用域里，此时 contextvar 已失效、读出来是默认值
    —— 表现为「同一个请求，链路末尾几行日志的 rid 变成 -」。
    解法是在生成器开头把 rid 捕获下来、finally 里用 logger.bind(request_id=...) 显式带上；
    这里保证那个显式值不会被 contextvar 的默认值冲掉。
    """
    if record["extra"].get("request_id", _DEFAULT_REQUEST_ID) == _DEFAULT_REQUEST_ID:
        record["extra"]["request_id"] = _request_id.get()
    if record["extra"].get("user_id", _DEFAULT_USER_ID) == _DEFAULT_USER_ID:
        record["extra"]["user_id"] = _user_id.get()


class InterceptHandler(logging.Handler):
    """把标准库 logging 桥接到 loguru（接管第三方库与残留的 stdlib logging）。"""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level = logger.level(record.levelname).name
        except (ValueError, AttributeError):
            level = record.levelno
        frame, depth = logging.currentframe(), 2
        while frame is not None and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1
        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


# ─────────────────────────────────────────────────────────────
# 日志目录解析：项目根 logs/ ，可用 LOG_DIR 覆盖
# ─────────────────────────────────────────────────────────────
_THIS_FILE = os.path.abspath(__file__)                                          # <backend>/app/utils/logger.py
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(_THIS_FILE)))    # <backend>


def _detect_repo_root(backend_dir: str) -> str:
    """从 backend/ 往上找仓库根。

    用「哨兵探测」而非硬编码 dirname 层级：层级一改（文件移动、加一层包）就静默指向错误目录。
    哨兵：父目录含 .git，或父目录下有 backend/ 子目录。
    容器场景（Dockerfile WORKDIR=/app）没有仓库根，回退到 backend 自身。
    """
    parent = os.path.dirname(backend_dir)
    if not parent or parent == backend_dir:      # 已到根（如 /）
        return backend_dir
    if os.path.exists(os.path.join(parent, ".git")) or \
       os.path.isdir(os.path.join(parent, "backend")):
        return parent
    return backend_dir


def _resolve_log_dir() -> str:
    """LOG_DIR 环境变量优先；否则 <仓库根>/logs。

    ⚠️ load_dotenv() 必须在这里调，不能只依赖 config.settings ——
       import 顺序不保证 settings 先执行，否则 LOG_DIR 读不到仓库根 .env 里的值。
    """
    try:
        from dotenv import load_dotenv
        load_dotenv()      # 幂等；无参时向上查找仓库根 .env；不覆盖已存在的环境变量
    except Exception:
        pass

    env_dir = os.getenv("LOG_DIR")
    if env_dir:
        return os.path.abspath(env_dir)
    return os.path.join(_detect_repo_root(_BACKEND_DIR), "logs")


_LOG_DIR = _resolve_log_dir()


def log_dir() -> str:
    """当前生效的日志目录（供启动日志与排查用）。"""
    return _LOG_DIR


def setup_logger() -> None:
    """幂等配置 loguru 三路 sink。import 时自动调用一次。"""
    if getattr(setup_logger, "_configured", False):
        return
    setup_logger._configured = True

    if not _HAS_LOGURU:
        return

    os.makedirs(_LOG_DIR, exist_ok=True)

    # ⚠️ 格式串里引用的 extra 字段，必须在 logger.configure(extra=...) 里有默认值，
    #    否则 loguru 在 emit 时抛 KeyError，整条日志变成一行 "Logging error in Loguru Handler"
    #    —— 表现为「日志根本没写」，极难定位。
    fmt = (
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level: <8}</level> | "
        "rid=<cyan>{extra[request_id]}</cyan> | "
        "user=<yellow>{extra[user_id]}</yellow> | "
        "task=<magenta>{extra[task_id]}</magenta> | "
        "<blue>{name}:{function}:{line}</blue> | "
        "<level>{message}</level>"
    )

    logger.remove()  # 清掉默认 sink

    # 1) stderr：开发可读（全量）
    #    enqueue=False：Windows 下 enqueue 走 multiprocessing 队列，进程退出时
    #    尾部日志可能来不及 flush（--reload 反复重启时更明显）。
    logger.add(sys.stderr, format=fmt, level=os.getenv("LOG_LEVEL", "DEBUG"),
               enqueue=False, backtrace=False, diagnose=False)

    # 2) 按日切分的全量业务日志
    logger.add(
        os.path.join(_LOG_DIR, "app-{time:YYYY-MM-DD}.log"),
        format=fmt, level="INFO", rotation="00:00",
        retention="30 days", compression="gz", encoding="utf-8", enqueue=True,
        backtrace=False, diagnose=False,
    )

    # 3) 仅 ERROR（带完整 traceback，便于排查）
    logger.add(
        os.path.join(_LOG_DIR, "error.log"),
        format=fmt, level="ERROR", rotation="00:00",
        retention="30 days", compression="gz", encoding="utf-8", enqueue=True,
        backtrace=True, diagnose=False,
    )

    # 默认 extra + patcher 注入 request_id / user_id（task_id / trace_id 走 logger.bind 覆盖）
    logger.configure(
        extra={"request_id": "-", "user_id": "-", "task_id": "-", "trace_id": "-"},
        patcher=_patch_record,
    )

    # 接管标准库 logging 的 root handler，桥接到 loguru
    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)

    # 压制第三方库的 INFO 噪音
    # httpx / httpcore 会把**每一次** HTTP 请求都打一条 INFO（含 LLM、embedding 调用），
    # 不压的话业务日志会被淹没。Boto3/urllib3 同理。
    for _noisy in ("httpx", "httpcore", "urllib3", "openai", "urllib3.connectionpool"):
        logging.getLogger(_noisy).setLevel(logging.WARNING)


# import 即完成幂等配置
setup_logger()
