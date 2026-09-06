from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

from app.routes import chat, run_task, workflow, health_check, status
from memory.scheduler import start_memory_scheduler
from llm.client import LLMClient

app = FastAPI(title="Quantum Agent Platform")


@app.exception_handler(Exception)
async def global_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"error": "内部错误，请重试", "detail": str(exc)}
    )

app.include_router(chat.router, prefix="/api/chat", tags=["chat"])
app.include_router(run_task.router, prefix="/api/task", tags=["task"])
app.include_router(workflow.router, prefix="/api/workflow", tags=["workflow"])
app.include_router(health_check.router, prefix="/api/health", tags=["health"])
app.include_router(status.router, prefix="/api/status", tags=["status"])

# 静态文件
app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.on_event("startup")
def _start_background_tasks():
    """启动后台记忆清理任务（每天 1 次）"""
    try:
        llm = LLMClient()
        start_memory_scheduler(llm, interval_seconds=86400)
    except Exception as e:
        print(f"[startup] 启动记忆调度器失败: {e}")


@app.get("/")
async def index():
    return FileResponse("app/static/index.html")
