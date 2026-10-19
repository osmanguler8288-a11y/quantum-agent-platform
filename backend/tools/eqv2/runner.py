"""EqV2 工具入口 —— 单点计算与结构优化。

替换了原先的占位桩（它 subprocess 调用一个并不存在的 `eqv2` CLI，还丢掉
stderr 与 returncode，失败时静默返回空串）。现在这两个函数直接调远程
HTTP 服务，见 tools/eqv2/client.py。

⚠️ 失败一律返回 `[错误] ...` 前缀的**字符串**，而不是抛异常。
   这是本项目的既有约定（见 tools/bash/runner.py），也是
   tools/instrumented_client.py 的埋点判定依据 —— 它的 `_ERR_PREFIX = "[错误]"`
   靠前缀把调用归类为 error。用 `[ERROR]`（如 tools/dip/runner.py）会被
   记成一次成功调用，工具库的调用统计就废了。

⚠️ 报告只出摘要，完整数据落盘到 data/eqv2/。原因见 tools/eqv2/parser.py
   的模块 docstring（executor 会把返回值原样塞进 prompt，全程不截断）。
"""

import re
from pathlib import Path

from app.utils.logger import logger
from config.settings import settings
from tools.eqv2 import parser as P
from tools.eqv2.client import (
    EqV2AuthError,
    EqV2Error,
    EqV2InputError,
    EqV2SubmitUncertain,
    get_client,
)

# 与 client 的默认值保持一致，用于报错文案
_MAX_FMAX = 5.0
_MAX_STEPS = 200
# Nginx 对请求体的限制
_MAX_BODY_BYTES = 128 * 1024

_SAFE_LABEL_RE = re.compile(r"[^0-9A-Za-z_\-]+")


def _safe_label(raw: str) -> str:
    """把任意名字收敛成安全的文件名片段。

    项目路径含中文，而 label 会进文件名 —— 保留中文反而更好读，
    所以只剔除路径分隔符与控制字符。
    """
    cleaned = _SAFE_LABEL_RE.sub("_", raw.strip()).strip("_")
    return cleaned[:60] or "eqv2"


def _resolve_xyz(xyz: str, input_file: str) -> tuple[str, str]:
    """把二选一的入参解析成 (xyz 文本, label)。抛 ValueError。"""
    has_xyz = bool(xyz and xyz.strip())
    has_file = bool(input_file and input_file.strip())

    if has_xyz and has_file:
        raise ValueError("xyz 与 input_file 只能二选一，请只传其中一个")
    if not has_xyz and not has_file:
        raise ValueError("必须提供 xyz（XYZ 文本）或 input_file（结构文件路径）之一")

    if has_file:
        text = P.read_xyz_text(input_file)
        return text, _safe_label(Path(input_file).stem)
    return P.normalize_xyz(xyz, "xyz"), "inline"


def _precheck(xyz: str) -> None:
    """出网前的本地预检：本地能判的错，不要拿服务端的 422 当流程控制。"""
    P.validate_xyz(xyz, settings.EQV2_MAX_ATOMS)
    if len(xyz.encode("utf-8")) > _MAX_BODY_BYTES:
        raise ValueError(
            f"XYZ 体积 {len(xyz.encode('utf-8'))} 字节，超过服务端 128KB 上限"
        )


def _describe_error(e: Exception) -> str:
    """把客户端异常翻译成给 LLM 和用户看的话。"""
    if isinstance(e, EqV2AuthError):
        return (
            f"[错误] {e}\n"
            f"  → 这是配置问题，不是计算问题。请在 .env 中设置正确的 "
            f"EQV2_API_KEY（当前 base_url={settings.EQV2_API_BASE_URL}）。"
        )
    if isinstance(e, EqV2InputError):
        return f"[错误] EqV2 服务拒绝了输入: {e}"
    if isinstance(e, EqV2SubmitUncertain):
        return (
            f"[错误] {e}\n"
            f"  → 不要直接重试提交。该作业可能已在服务端创建并占用唯一的计算槽位；"
            f"请稍后用 /v1/jobs 查询，或联系服务管理员确认。"
        )
    if isinstance(e, EqV2Error):
        return f"[错误] {e}"
    return f"[错误] EqV2 调用异常: {type(e).__name__}: {e}"


# ─────────────────────────────────────────────────────────────
# 工具 1：单点计算
# ─────────────────────────────────────────────────────────────

def run_eqv2_predict(xyz: str = "", input_file: str = "") -> str:
    """用 EqV2 31M 机器学习势算单点能量与原子力。

    参数:
        xyz:        XYZ 文本（首行原子数，第二行注释，随后 '元素 x y z'）
        input_file: 结构文件路径，支持 .xyz 与 .gjf/.com（Gaussian 输入）
                    —— 与 xyz 二选一

    返回:
        格式化报告（纯文本）。完整数据另存为 data/eqv2/<label>_predict.json。

    典型用途：用户问"这个结构的能量是多少""受力大不大""键长键角多少"。
    若用户想要的是找稳定构型，应改用 run_eqv2_relax。
    """
    try:
        xyz_text, label = _resolve_xyz(xyz, input_file)
        _precheck(xyz_text)
    except ValueError as e:
        return f"[错误] 输入无效: {e}"

    natoms = P.count_atoms(xyz_text)
    logger.bind(component="eqv2").info(
        "[eqv2] predict | label={} | natoms={}", label, natoms
    )

    try:
        client = get_client()
        data = client.predict(xyz_text)
        model = ""
        try:
            model = client.models().get("model", "")
        except EqV2Error:
            pass                       # 拿不到模型名不影响主结果
    except Exception as e:             # noqa: BLE001 - 统一转成 [错误] 字符串
        logger.bind(component="eqv2").opt(exception=True).warning(
            "[eqv2] predict 失败 | label={} | natoms={}", label, natoms
        )
        return _describe_error(e)

    artifacts = {}
    try:
        path = P.save_json(
            {"label": label, "model": model, "energy_ev": data.get("energy_ev"),
             "natoms": data.get("natoms"), "elements": data.get("elements"),
             "forces_ev_per_ang": data.get("forces_ev_per_ang"),
             "bond_analysis": data.get("bond_analysis")},
            Path(settings.EQV2_DATA_DIR) / f"{label}_predict.json",
        )
        artifacts["原始 JSON"] = str(path)
    except Exception:
        logger.bind(component="eqv2").opt(exception=True).warning(
            "[eqv2] predict 产物写盘失败（不影响本次结果）| label={}", label
        )

    report = P.format_predict_report(data, label, model=model)
    if artifacts:
        report += "\n  [完整产物]\n" + "\n".join(
            f"    {k}: {v}" for k, v in artifacts.items()
        )
    return report


# ─────────────────────────────────────────────────────────────
# 工具 2：结构优化
# ─────────────────────────────────────────────────────────────

def run_eqv2_relax(xyz: str = "", input_file: str = "",
                   fmax: float = 0.05, max_steps: int = 200) -> str:
    """用 EqV2 31M 机器学习势做几何优化（BFGS），异步作业。

    参数:
        xyz:        XYZ 文本
        input_file: 结构文件路径（.xyz / .gjf / .com）—— 与 xyz 二选一
        fmax:       收敛力阈值，单位 eV/Å，须在 (0, 5.0]，默认 0.05
        max_steps:  最大优化步数，范围 1~200，默认 200

    返回:
        格式化报告（纯文本摘要）。优化后结构、完整轨迹、原始结果另存到
        data/eqv2/。

    ⚠️ 报告中的 converged 才是收敛判据；作业状态 completed 只表示流程跑完。
    ⚠️ 服务端单任务执行，耗时随原子数与步数增长（实测水分子 200 步约 27 秒）。
    """
    try:
        xyz_text, label = _resolve_xyz(xyz, input_file)
        _precheck(xyz_text)
    except ValueError as e:
        return f"[错误] 输入无效: {e}"

    # 参数范围在本地判定，与服务端 Pydantic 约束保持一致
    try:
        fmax = float(fmax)
        max_steps = int(max_steps)
    except (TypeError, ValueError):
        return "[错误] 输入无效: fmax 必须是数字，max_steps 必须是整数"
    if not (0.0 < fmax <= _MAX_FMAX):
        return f"[错误] 输入无效: fmax 须在 (0, {_MAX_FMAX}] 之间，当前 {fmax}"
    if not (1 <= max_steps <= _MAX_STEPS):
        return f"[错误] 输入无效: max_steps 须在 1~{_MAX_STEPS} 之间，当前 {max_steps}"

    natoms = P.count_atoms(xyz_text)
    logger.bind(component="eqv2").info(
        "[eqv2] relax | label={} | natoms={} | fmax={} | max_steps={}",
        label, natoms, fmax, max_steps,
    )

    client = get_client()
    try:
        job_id = client.submit_relax(xyz_text, fmax=fmax, max_steps=max_steps)
    except Exception as e:             # noqa: BLE001
        logger.bind(component="eqv2").opt(exception=True).warning(
            "[eqv2] relax 提交失败 | label={} | natoms={}", label, natoms
        )
        return _describe_error(e)

    def _progress(job: dict) -> None:
        logger.bind(component="eqv2").debug(
            "[eqv2] job={} 进度 | status={}", job_id, job.get("status")
        )

    try:
        job = client.wait_for_job(job_id, on_progress=_progress)
    except Exception as e:             # noqa: BLE001
        logger.bind(component="eqv2").opt(exception=True).warning(
            "[eqv2] relax 轮询失败 | job_id={}", job_id
        )
        return (
            f"{_describe_error(e)}\n"
            f"  → 作业 ID: {job_id}（可能仍在服务端运行，可稍后重查）"
        )

    # ── 落盘：结构 / 轨迹 / 原始结果 ──
    artifacts = {}
    data_dir = Path(settings.EQV2_DATA_DIR)
    result = job.get("result") or {}

    if job.get("status") == "completed":
        try:
            structure = client.get_structure(job_id)
            artifacts["优化后结构"] = str(
                P.save_text(structure, data_dir / f"{label}_relaxed.xyz")
            )
        except Exception:
            # 结构下载失败不该让整个优化结果作废 —— 摘要仍然有价值
            logger.bind(component="eqv2").opt(exception=True).warning(
                "[eqv2] 结构下载失败（摘要仍返回）| job_id={}", job_id
            )

    try:
        if result.get("trajectory"):
            artifacts["轨迹 CSV"] = str(P.save_trajectory_csv(
                result["trajectory"], data_dir / f"{label}_trajectory.csv"
            ))
        artifacts["原始结果"] = str(P.save_json(
            job, data_dir / f"{label}_relax_job.json"
        ))
    except Exception:
        logger.bind(component="eqv2").opt(exception=True).warning(
            "[eqv2] relax 产物写盘失败（不影响本次结果）| job_id={}", job_id
        )

    model = ""
    try:
        model = client.models().get("model", "")
    except EqV2Error:
        pass

    logger.bind(component="eqv2").info(
        "[eqv2] relax 完成 | job_id={} | status={} | converged={} | nsteps={}",
        job_id, job.get("status"), result.get("converged"), result.get("nsteps"),
    )

    return P.format_relax_report(job, label, model=model, artifacts=artifacts)


def run_eqv2(input_file: str, output_file: str = "") -> str:
    """已废弃的兼容入口 —— 旧契约是 (input_file, output_file)。

    保留它只为让历史调用点（scripts/test_tools.py）不至于直接 ImportError。
    新代码请用 run_eqv2_predict / run_eqv2_relax。
    """
    logger.bind(component="eqv2").warning(
        "[eqv2] run_eqv2 是已废弃的兼容入口，请改用 eqv2_predict / eqv2_relax"
    )
    return run_eqv2_relax(input_file=input_file)
