import json as json_module
import uuid
from fastapi import APIRouter
from fastapi.responses import JSONResponse, StreamingResponse

from app.schemas.request import WorkflowRequest
from llm.client import LLMClient
from agent.planner import Planner
from agent.executor import Executor
from agent.critic import Critic
from tools.register_all import build_client
from agent.state import AgentState
from workflow.graph import build_workflow
from rag.embedder import Embedder
from rag.vector_db import MilvusClient
from rag.retriever import Retriever
from db.redis_client import RedisClient

router = APIRouter()

# 启动时初始化一次
llm = LLMClient()
mcp = build_client()
planner = Planner(llm)
executor = Executor(mcp, llm=llm)
critic = Critic(llm)
embedder = Embedder()
vector_db = MilvusClient()
retriever = Retriever(embedder, vector_db)
redis_client = RedisClient()
app = build_workflow(planner, executor, critic, retriever=retriever)

MAX_RETRIES = 3


@router.post("/run")
async def run_workflow(req: WorkflowRequest):
    task_id = req.workflow_id or str(uuid.uuid4())[:8]
    session_id = req.session_id or str(uuid.uuid4())[:8]
    user_query = req.input_data.get("user_query", "")

    # 多轮：读历史 + 拼上下文
    messages = redis_client.get_history(session_id)
    history_text = format_history(messages)

    result = app.invoke({
        "task_id": task_id,
        "user_query": user_query,
        "current_step": 0,
        "retry_count": 0,
        "history_text": history_text,
    })

    # 多轮：保存历史
    messages.append({"role": "user", "content": user_query})
    messages.append({"role": "assistant", "content": result.get("thinking", "")})
    redis_client.save_history(session_id, messages)

    return JSONResponse({
        "task_id": task_id,
        "session_id": session_id,
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


def format_history(messages: list[dict]) -> str:
    """把 messages 列表转成纯文本，方便注入 planner prompt"""
    if not messages:
        return "（无历史对话）"
    lines = []
    for m in messages:
        role = "用户" if m["role"] == "user" else "助手"
        lines.append(f"{role}: {m['content']}")
    return "\n".join(lines)


@router.post("/stream")
async def stream_workflow(req: WorkflowRequest):
    task_id = req.workflow_id or str(uuid.uuid4())[:8]
    user_query = req.input_data.get("user_query", "")
    session_id = req.session_id or str(uuid.uuid4())[:8]

    def event_stream():
        try:
            state = AgentState(task_id=task_id, user_query=user_query)
            retry_count = 0

            # ---- 从 Redis 取历史 ----
            messages = redis_client.get_history(session_id)
            state.history = messages

            # ---- phase 0: RAG 检索 ----
            try:
                rag_context = retriever.retrieve_as_context(user_query)
                yield sse({"event": "rag_done", "data": {"context_len": len(rag_context)}})
            except Exception as e:
                rag_context = "（RAG 检索不可用，请检查 Milvus 是否启动）"
                yield sse({"event": "rag_done", "data": {"context_len": len(rag_context), "warning": str(e)}})

            # ---- 拼接完整上下文：对话历史 + 参考资料 ----
            history_text = format_history(messages)
            full_context = f"## 对话历史\n{history_text}\n\n## 参考资料\n{rag_context}"

            # ---- phase 1: planning ----
            for event in planner.plan_stream(state, context=full_context):
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
                    messages.append({"role": "user", "content": user_query})
                    messages.append({"role": "assistant", "content": state.final_result or state.thinking})
                    redis_client.save_history(session_id, messages)

                    yield sse({"event": "done", "data": {"status": "passed", "session_id": session_id}})
                    return

                retry_count += 1
                if retry_count >= MAX_RETRIES:
                    messages.append({"role": "user", "content": user_query})
                    messages.append({"role": "assistant", "content": state.final_result or state.thinking})
                    redis_client.save_history(session_id, messages)

                    yield sse({"event": "done", "data": {"status": "max_retries", "retry_count": retry_count, "session_id": session_id}})
                    return

                yield sse({"event": "retry", "data": {"retry_count": retry_count}})

        except Exception as e:
            # 友好降级：把异常通过 SSE 告诉前端，而不是直接断连
            yield sse({"event": "error", "data": {"message": f"服务内部异常，请重试。错误: {str(e)}"}})

    return StreamingResponse(event_stream(), media_type="text/event-stream")
