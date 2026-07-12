import json as json_module
import uuid
from fastapi import APIRouter
from fastapi.responses import JSONResponse, StreamingResponse

from app.schemas.request import WorkflowRequest
from llm.client import LLMClient
from agent.planner import Planner
from agent.executor import Executor
from agent.critic import Critic
from agent.mcp_client import MCPClient
from agent.state import AgentState
from workflow.graph import build_workflow

router = APIRouter()

# 启动时初始化一次
llm = LLMClient()
mcp = MCPClient()
planner = Planner(llm)
executor = Executor(mcp, llm=llm)
critic = Critic(llm)
app = build_workflow(planner, executor, critic)

MAX_RETRIES = 3


@router.post("/run")
async def run_workflow(req: WorkflowRequest):
    task_id = req.workflow_id or str(uuid.uuid4())[:8]
    user_query = req.input_data.get("user_query", "")

    result = app.invoke({
        "task_id": task_id,
        "user_query": user_query,
        "current_step": 0,
        "retry_count": 0,
    })

    return JSONResponse({
        "task_id": task_id,
        "status": result.get("status", "unknown"),
        "thinking": result.get("thinking", ""),
        "plan": result.get("plan", []),
        "results": result.get("results", []),
        "verdict": result.get("verdict", {}),
        "retry_count": result.get("retry_count", 0),
    })


def sse(event: dict) -> str:
    """把事件 dict 转成 SSE 格式"""
    return f"data: {json_module.dumps(event, ensure_ascii=False)}\n\n"


@router.post("/stream")
async def stream_workflow(req: WorkflowRequest):
    task_id = req.workflow_id or str(uuid.uuid4())[:8]
    user_query = req.input_data.get("user_query", "")

    def event_stream():
        state = AgentState(task_id=task_id, user_query=user_query)
        retry_count = 0

        # ---- phase 1: planning ----
        for event in planner.plan_stream(state):
            yield sse(event)

        # ---- phase 2: execute + critic loop ----
        while True:
            # execute
            for event in executor.execute_stream(state):
                yield sse(event)

            # critic
            step = state.plan[-1] if state.plan else {}
            result = state.results[-1]["output"] if state.results else {}
            verdict = critic.review(step=step, result=result, task=user_query)
            yield sse({"event": "verdict_done", "data": verdict})

            if verdict.get("passed"):
                yield sse({"event": "done", "data": {"status": "passed"}})
                return

            retry_count += 1
            if retry_count >= MAX_RETRIES:
                yield sse({"event": "done", "data": {"status": "max_retries", "retry_count": retry_count}})
                return

            yield sse({"event": "retry", "data": {"retry_count": retry_count}})

    return StreamingResponse(event_stream(), media_type="text/event-stream")
