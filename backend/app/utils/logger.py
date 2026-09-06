"""项目统一日志模块（loguru 驱动）。

用法：
    from app.utils.logger import logger, mask_sensitive, set_request_id

规范（见 logging skill）：
    - 一切日志走本模块的 logger，禁止 print / 裸标准库 logging
    - 状态变更打 info，失败分支 raise 前打 warning，异常块打 exception
    - 记录入参先过 mask_sensitive 脱敏
"""
import logging
import os
import re
import sys
from contextvars import ContextVar

from loguru import logger

# ─────────────────────────────────────────────────────────────
# request_id 每请求写入（中间件调用 set_request_id）；
# trace_id 是 AI 留痕基线，走 logger.bind(trace_id=...) 覆盖。
# ─────────────────────────────────────────────────────────────
_request_id: ContextVar[str] = ContextVar("request_id", default="-")

# 敏感字段名 / 敏感键值对（脱敏用）
_SENSITIVE_KEY = re.compile(
    r"(password|passwd|pwd|token|api_key|apikey|authorization|secret|credential|access_key|secret_key)",
    re.IGNORECASE,
)
_SENSITIVE_PAIR = re.compile(
    r"(?i)(password|passwd|pwd|token|api_key|apikey|authorization|secret|credential|access_key|secret_key)"
    r"\s*[=:]\s*([^&\s,;]+)"
)

# 日志目录固定写到 backend/logs/（不依赖运行 cwd）
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_LOG_DIR = os.path.join(_BASE_DIR, "logs")


def set_request_id(rid: str) -> None:
    """中间件每请求调用一次，写入当前请求的 request_id。"""
    _request_id.set(rid)


def get_request_id() -> str:
    return _request_id.get()


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
    """loguru patcher：每条日志注入当前 request_id（来自 contextvar）。"""
    record["extra"]["request_id"] = _request_id.get()


class InterceptHandler(logging.Handler):
    """把标准库 logging 桥接到 loguru（接管现存 llmops/tools 的 logging）。"""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno
        frame, depth = logging.currentframe(), 2
        while frame is not None and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1
        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


def setup_logger() -> None:
    """幂等配置 loguru 三路 sink。import 时自动调用一次。"""
    if getattr(setup_logger, "_configured", False):
        return

    os.makedirs(_LOG_DIR, exist_ok=True)

    fmt = (
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level: <8}</level> | "
        "rid=<cyan>{extra[request_id]}</cyan> | "
        "<blue>{name}:{function}:{line}</blue> | "
        "tid=<magenta>{extra[trace_id]}</magenta> | "
        "<level>{message}</level>"
    )

    logger.remove()  # 清掉默认 sink

    # 1) stderr：开发可读（全量）
    logger.add(sys.stderr, format=fmt, level="DEBUG", enqueue=True)

    # 2) 按日切分的全量业务日志
    logger.add(
        os.path.join(_LOG_DIR, "app-{time:YYYY-MM-DD}.log"),
        format=fmt, level="INFO", rotation="00:00",
        retention="30 days", compression="gz", encoding="utf-8", enqueue=True,
    )

    # 3) 仅 ERROR
    logger.add(
        os.path.join(_LOG_DIR, "error.log"),
        format=fmt, level="ERROR", rotation="00:00",
        retention="30 days", compression="gz", encoding="utf-8", enqueue=True,
    )

    # 默认 extra + patcher 注入 request_id（trace_id 走 logger.bind 覆盖）
    logger.configure(extra={"request_id": "-", "trace_id": "-"}, patcher=_patch_record)

    # 接管标准库 logging 的 root handler，桥接到 loguru
    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)

    setup_logger._configured = True


# import 即完成幂等配置
setup_logger()
