from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.routes import chat, run_task, workflow, health_check, status

app = FastAPI(title="Quantum Agent Platform")

app.include_router(chat.router, prefix="/api/chat", tags=["chat"])
app.include_router(run_task.router, prefix="/api/task", tags=["task"])
app.include_router(workflow.router, prefix="/api/workflow", tags=["workflow"])
app.include_router(health_check.router, prefix="/api/health", tags=["health"])
app.include_router(status.router, prefix="/api/status", tags=["status"])

# 静态文件
app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.get("/")
async def index():
    return FileResponse("app/static/index.html")
