"""每请求的工具调用上下文。

⚠️ 为什么存「可变对象」而不是几个独立的 ContextVar：

    SSE 生成器由 Starlette 抛到线程池执行，anyio 每次 next(gen) 都 copy_context()，
    生成器体里对 ContextVar 的 **set()** 在下一个 yield 后就失效（写进了一次性副本）。
    但**引用**不会失效 —— 拿到对象后原地修改属性可以跨 yield 存活。

    所以在端点体（上下文正确的时机）用 start_invocation() 创建对象，
    之后在生成器内部任意深度都能通过 current_invocation() 拿到同一个对象并递增计数。

注意：本对象只在**同步**代码路径里使用（executor / MCPClient 都在线程池线程），
     不要跨线程共享同一个实例做写入。
"""
from contextvars import ContextVar
from dataclasses import dataclass, field


@dataclass
class InvocationContext:
    user_id: str = "default_user"
    session_id: str | None = None
    task_id: str | None = None
    task_title: str | None = None
    seq: int = 0          # 本请求内第几次工具调用（≈ 执行序号，非 plan 步骤号）


_ctx: ContextVar[InvocationContext | None] = ContextVar("invocation_ctx", default=None)


def start_invocation(**kwargs) -> InvocationContext:
    """在**端点体**调用（不能放在生成器体内，理由见模块 docstring）。"""
    ctx = InvocationContext(**kwargs)
    _ctx.set(ctx)
    return ctx


def current_invocation() -> InvocationContext | None:
    return _ctx.get()
