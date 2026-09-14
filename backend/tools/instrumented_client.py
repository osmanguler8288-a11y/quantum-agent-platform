"""MCPClient 的可观测包装 —— 统一工具调用入口的埋点。

设计取舍：**包装在 MCPClient 边界，而不是 executor._execute_with_retry 内部**。

    理由不是语义上的（加计时不改控制流），而是工程上的：
      1. agent/executor.py 已被划为主链路禁区，diff 里出现它会把 review 成本
         从「看 1 个新文件」变成「逐行确认没动重试与状态机」。
      2. P5 注定要重写 _execute_with_retry（修 retryable 判定、统一两个方法的失败行为），
         内联埋点届时必须重新验证；写在 MCP 边界的包装可以原样存活。
      3. 包装天然覆盖未来所有调用方（_call_remote 落地后也一样）。

⚠️ 埋点与调用语义完全解耦：
    - 异常原样 re-raise（不吞）
    - 写库失败只 warning（红线 ❌10：可观测性不该影响可用性）
"""
import time
from datetime import datetime, timezone

from app.utils.context import current_invocation
from app.utils.logger import logger
from db.invocation_repo import params_digest, record_invocation

# ⚠️ 已知偏差：内置 runner 用「返回 '[错误] ...' 字符串」表示失败而非抛异常
#    （见 tools/file_tools/runner.py 等），MCPClient 会把这类结果归类为 success。
#    这里做一次前缀判定让统计可用，但它是**启发式而非契约** ——
#    真正的统一修复在 P5（让 runner 抛异常或返回统一 envelope）。
_ERR_PREFIX = "[错误]"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class InstrumentedMCPClient:
    """透明代理：转发所有属性到真实 client，只在 call() 上注入埋点。"""

    def __init__(self, inner):
        self._inner = inner

    # registry / register_remote / list_tools 等全部透传。
    # 只在常规属性查找失败时触发，不会遮蔽下面定义的 call()。
    def __getattr__(self, item):
        return getattr(self._inner, item)

    def call(self, tool_name: str, params: dict) -> dict:
        ctx = current_invocation()
        started = _now()
        t0 = time.perf_counter()
        raised = None

        try:
            result = self._inner.call(tool_name, params)
        except BaseException as e:          # noqa: BLE001 - 原样透传，只记录
            raised = e
            result = None

        duration_ms = int((time.perf_counter() - t0) * 1000)

        if raised is not None:
            self._record(ctx, tool_name, params, "error", duration_ms, started,
                         error_code=type(raised).__name__, error_message=str(raised))
            raise raised                     # ← 不改变调用语义

        status = "error" if result.get("status") == "error" else "success"
        # 启发式：识别 runner 用字符串表达的失败
        if status == "success" and isinstance(result.get("result"), str) \
                and result["result"].lstrip().startswith(_ERR_PREFIX):
            status = "error"

        self._record(
            ctx, tool_name, params, status, duration_ms, started,
            error_message=None if status == "success" else (
                result.get("message") or (result.get("result") or "")[:200]
            ),
        )
        return result

    # ─────────────────────────────────────────────────
    def _record(self, ctx, tool_name, params, status, duration_ms, started,
                error_code=None, error_message=None) -> None:
        try:
            seq = None
            if ctx is not None:
                ctx.seq += 1                 # ← 可变对象，跨 yield 存活
                seq = ctx.seq
            record_invocation(
                tool_name=tool_name,
                status=status,
                duration_ms=duration_ms,
                started_at=started,
                finished_at=_now(),
                user_id=ctx.user_id if ctx else "default_user",
                session_id=ctx.session_id if ctx else None,
                task_title=ctx.task_title if ctx else None,
                step_index=seq,
                error_code=error_code,
                error_message=error_message,
                params_digest=params_digest(params if isinstance(params, dict) else {}),
            )
        except Exception:
            # 双重保险：record_invocation 内部已容错，这里再兜一层，
            # 保证「埋点绝不影响工具调用」这条红线不被任何路径突破。
            logger.opt(exception=True).warning(
                "[tools] 埋点记录失败（不影响本次调用）tool={}", tool_name
            )
