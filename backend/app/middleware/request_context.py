"""请求上下文中间件（纯 ASGI）。

作用：为每个 HTTP 请求生成/透传 request_id，写入日志上下文，并记录请求总耗时与状态码。

⚠️ 为什么必须用纯 ASGI 而不是 `BaseHTTPMiddleware`：
    1. BaseHTTPMiddleware 把下游应用放进独立的 anyio task，会重新包装
       StreamingResponse.body_iterator —— 对 SSE（/api/workflow/stream）有丢事件、
       断连处理变形的真实风险。
    2. 纯 ASGI 版本与下游处于同一个 context，contextvar 在这里 set 之后，
       下游端点**以及被 Starlette 抛到线程池的 SSE 生成器**都能读到。
       （实测：每次 next(gen) 都是独立的 copy_context() 快照，所以 set 的位置必须在
        中间件或端点体；放进生成器体内的话，第二条日志开始就会退回默认值。）
"""
import time
import uuid

from app.utils.logger import logger, set_request_id, set_user_id


class RequestContextMiddleware:
    """写入 request_id / user_id，并记录请求耗时与状态码。"""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        # WebSocket / lifespan 直接透传
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = {
            k.decode("latin-1").lower(): v.decode("latin-1")
            for k, v in scope.get("headers", [])
        }

        # 优先透传上游（Go 网关）的 X-Request-ID，便于跨服务串联同一次请求
        request_id = headers.get("x-request-id") or uuid.uuid4().hex[:12]
        user_id = headers.get("x-user-id") or "default_user"
        set_request_id(request_id)
        set_user_id(user_id)

        # 捕获响应状态码：在 send 上挂一层，只读不改
        status_code = None

        async def send_wrapper(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        t0 = time.perf_counter()
        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            # 这里能捕获的是「响应头尚未发出」的异常（如路由依赖、非流式端点）。
            # ⚠️ StreamingResponse 生成器体内部的异常**不会**流到这里 —— 那时
            #    http.response.start 已经发出，只能由端点自己的 try/except 兜底。
            logger.bind(path=scope.get("path", "?")).opt(exception=True).error(
                "[http] 未捕获异常 {} {}", scope.get("method", "?"), scope.get("path", "?")
            )
            raise
        finally:
            elapsed_ms = (time.perf_counter() - t0) * 1000
            level = "warning" if (status_code or 500) >= 400 else "info"
            getattr(logger, level)(
                "[http] {} {} | status={} | {:.0f}ms",
                scope.get("method", "?"), scope.get("path", "?"),
                status_code if status_code is not None else "-", elapsed_ms,
            )
