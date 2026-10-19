from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

from app.middleware.request_context import RequestContextMiddleware
from app.routes import chat, run_task, workflow, health_check, status, tools, conversations, descriptors
from app.utils.logger import logger, log_dir
from memory.scheduler import start_memory_scheduler
from llm.client import LLMClient

app = FastAPI(title="Quantum Agent Platform")

# 请求上下文（request_id / user_id 注入日志 + 总耗时）。
# 必须是纯 ASGI 中间件，BaseHTTPMiddleware 会重新包装 SSE 的 body_iterator。
app.add_middleware(RequestContextMiddleware)


@app.exception_handler(Exception)
async def global_handler(request: Request, exc: Exception):
    logger.bind(path=request.url.path, method=request.method).opt(exception=True).error(
        "[api] 未捕获异常 {} {}", request.method, request.url.path
    )
    return JSONResponse(
        status_code=500,
        content={"error": "内部错误，请重试", "detail": str(exc)}
    )


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    """把 FastAPI 默认的 422 格式统一成项目的错误契约。

    ⚠️ 为什么需要：默认响应是 {"detail": [ {...}, {...} ]} —— detail 是**数组**。
       前端 frontend/src/api/client.ts 的 `data?.error || data?.detail` 会把这个数组
       当成消息渲染。这里改成：
         error  → 人类可读的字符串（前端直接显示）
         detail → 保留原始结构数组（机器可读，供调试）
    """
    problems = []
    for err in exc.errors():
        loc = ".".join(str(x) for x in err.get("loc", []) if x != "body")
        msg = err.get("msg", "").removeprefix("Value error, ")
        problems.append(f"{loc}: {msg}" if loc else msg)
    readable = "；".join(problems) or "请求参数校验失败"

    logger.bind(path=request.url.path).warning("[api] 参数校验失败: {}", readable)
    return JSONResponse(
        status_code=422,
        content={
            "error": readable,
            "code": "VALIDATION_ERROR",
            "detail": jsonable_encoder(exc.errors()),
        },
    )

app.include_router(chat.router, prefix="/api/chat", tags=["chat"])
app.include_router(run_task.router, prefix="/api/task", tags=["task"])
app.include_router(workflow.router, prefix="/api/workflow", tags=["workflow"])
app.include_router(health_check.router, prefix="/api/health", tags=["health"])
app.include_router(status.router, prefix="/api/status", tags=["status"])
app.include_router(tools.router, prefix="/api/tools", tags=["tools"])
app.include_router(conversations.router, prefix="/api/conversations", tags=["conversations"])
app.include_router(descriptors.router, prefix="/api/descriptors", tags=["descriptors"])

# 静态文件
app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.on_event("startup")
def _start_background_tasks():
    """启动：① seed 工具库 ② 重建 registry ③ 起记忆调度器"""
    logger.info("[startup] Quantum Agent Platform 后端启动 | 日志目录={}", log_dir())

    # ① 工具库 seed（幂等）。失败不阻止启动 —— 工具库降级为不可用，其余功能照常。
    try:
        from db.seed_tools import seed_all
        stats = seed_all()
        logger.info("[startup] 工具库 seed 完成 {}", stats)
    except Exception:
        logger.opt(exception=True).error("[startup] 工具库 seed 失败，工具库降级（应用继续启动）")

    # ② 从 DB 重建 registry，让「DB 为真源」真正生效。
    try:
        from tools.tool_registry_loader import bind, reload_registry
        from app.routes.workflow import mcp
        bind(mcp)
        ok, warning = reload_registry()
        if not ok:
            logger.warning("[startup] registry 重建失败，沿用代码注册的版本: {}", warning)
    except Exception:
        logger.opt(exception=True).error("[startup] registry 重建异常，沿用旧 registry")

    # 埋点表是唯一会无限增长的表，启动时清理一次过期的
    try:
        from db.invocation_repo import purge_older_than
        purge_older_than(90)
    except Exception:
        logger.opt(exception=True).warning("[startup] 埋点清理失败（不影响启动）")

    # ③ 记忆调度器
    try:
        llm = LLMClient()
        start_memory_scheduler(llm, interval_seconds=86400)
        logger.info("[startup] 记忆调度器已启动（间隔 86400s）")
    except Exception:
        logger.opt(exception=True).warning("[startup] 启动记忆调度器失败，记忆自动整理不可用")


@app.get("/")
async def index():
    return FileResponse("app/static/index.html")
