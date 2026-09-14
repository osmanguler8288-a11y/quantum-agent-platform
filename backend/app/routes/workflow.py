import json as json_module
import time
import uuid
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from app.schemas.request import WorkflowRequest
from app.utils.logger import logger, get_request_id
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
from db.redis_client import RedisClient, NullRedis
from app.utils.context import start_invocation
from tools.instrumented_client import InstrumentedMCPClient

router = APIRouter()


def _safe(label: str, factory, fallback=None):
    """模块级单例的安全构造。

    这些单例在 **import 期**创建，任何一个抛异常都会让 `uvicorn app.main:app`
    直接起不来、且不留任何日志。最典型的是 Embedder()：EMBED_API_KEY 为空时
    openai SDK 构造即抛。外部依赖不可用应当降级，而不是阻止整个应用启动。
    """
    try:
        return factory()
    except Exception:
        logger.bind(component=label).opt(exception=True).error(
            "[startup] {} 初始化失败，相关能力降级", label
        )
        return fallback


# 启动时初始化一次
llm = _safe("LLMClient", LLMClient)
# ⚠️ 用可观测代理包装：工具调用的耗时/成败埋点在 MCPClient 边界完成，
#    agent/executor.py 因此保持零 diff。
mcp = _safe("MCPClient", lambda: InstrumentedMCPClient(build_client()))
planner = Planner(llm)
executor = Executor(mcp, llm=llm)
critic = Critic(llm)
embedder = _safe("Embedder", Embedder)
vector_db = _safe("MilvusClient", MilvusClient)
retriever = Retriever(embedder, vector_db) if (embedder and vector_db) else None
# Redis 用空对象兜底：下面多处**直接**调用它，为 None 会 AttributeError 打断对话链路
redis_client = _safe("RedisClient", RedisClient, fallback=NullRedis())


def _get_memory_tool_for_user(user_id: str):
    """为指定 user_id 创建 MemoryTool（不走 thread-local，避免异步污染）"""
    from memory.tool import MemoryTool
    return MemoryTool(user_id=str(user_id), llm=llm)


app = build_workflow(
    planner, executor, critic,
    retriever=retriever,
    memory_tool_getter=lambda: _get_memory_tool_for_user("default_user"),   # graph 不直接用
)

MAX_RETRIES = 3


def _inject_user(request: Request):
    """从 Go 网关注入的 X-User-ID header 取用户 ID"""
    user_id = request.headers.get("X-User-ID") or "default_user"
    return user_id


@router.post("/run")
async def run_workflow(req: WorkflowRequest, request: Request):
    user_id = _inject_user(request)
    task_id = req.workflow_id or str(uuid.uuid4())[:8]
    session_id = req.session_id or str(uuid.uuid4())[:8]
    user_query = req.input_data.get("user_query", "")

    # 多轮：读历史 + 拼上下文
    messages = redis_client.get_history(session_id)
    history_text = format_history(messages)

    result = app.invoke({
        "task_id": task_id,
        "user_id": user_id,
        "user_query": user_query,
        "current_step": 0,
        "retry_count": 0,
        "history_text": history_text,
    })

    # 多轮：保存历史
    messages.append({"role": "user", "content": user_query})
    messages.append({"role": "assistant", "content": result.get("thinking", "")})
    redis_client.save_history(session_id, messages)

    # 自动存为情景记忆
    try:
        mem_tool = _get_memory_tool_for_user(str(user_id))
        mem_tool.set_session(session_id)
        mem_tool.memory_manager.add_memory(
            content=f"用户: {user_query}\n助手: {result.get('thinking', '')[:500]}",
            memory_type="episodic",
            importance=0.6,
            session_id=session_id,
        )
    except Exception as e:
        logger.bind(task_id=task_id).warning("[memory] 自动存记忆失败: {}", e)

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
async def stream_workflow(req: WorkflowRequest, request: Request):
    user_id = _inject_user(request)
    task_id = req.workflow_id or str(uuid.uuid4())[:8]
    user_query = req.input_data.get("user_query", "")
    session_id = req.session_id or str(uuid.uuid4())[:8]

    # ⚠️ 必须在**端点体**创建（不能放进生成器体内）：这是工具调用埋点能拿到
    #    user/session/task 上下文的唯一时机 —— 生成器跑在线程池，体内 set 的
    #    ContextVar 在下一个 yield 后即失效。详见 app/utils/context.py。
    start_invocation(
        user_id=str(user_id), session_id=session_id,
        task_id=task_id, task_title=user_query[:50],
    )

    def event_stream():
        t0 = time.perf_counter()
        # ⚠️ 必须在生成器**开头**捕获 request_id：
        #    客户端中途断连时生成器被 close()，finally 会跑在一个已脱离请求上下文的作用域里，
        #    contextvar 那时已失效。捕获下来再显式 bind，才能保证末尾日志仍能按 rid 串联。
        rid = get_request_id()
        # ⚠️ 这几个名字必须在 try 之外初始化：finally 会引用它们，
        #    否则异常路径上会抛 UnboundLocalError，反而把真实异常盖掉。
        state = None
        retry_count = 0
        outcome = "aborted"          # 客户端中途断连时保持此值

        try:
            state = AgentState(task_id=task_id, user_query=user_query)

            # ---- 为本请求创建专属 MemoryTool（user_id 隔离，避免 thread-local 异步污染）----
            mem_tool = _get_memory_tool_for_user(str(user_id))
            mem_tool.set_session(session_id)

            # ---- 从 Redis 取历史 ----
            messages = redis_client.get_history(session_id)
            state.history = messages

            # ---- phase -1: 长期记忆检索（user_id 隔离）----
            memory_context = ""
            try:
                memory_results = mem_tool.memory_manager.retrieve_memories(
                    query=user_query,
                    limit=3,
                    memory_types=["episodic", "semantic"],
                    min_importance=0.3,
                )
                if memory_results:
                    lines = []
                    for m in memory_results:
                        lines.append(f"- [{m.memory_type}/{m.importance:.2f}] {m.content[:200]}")
                    memory_context = "\n".join(lines)
                yield sse({"event": "memory_done", "data": {"count": len(memory_results) if memory_results else 0}})
            except Exception as e:
                logger.bind(task_id=task_id).warning("[memory] 长期记忆检索失败，跳过: {}", e)
                yield sse({"event": "memory_done", "data": {"count": 0, "warning": str(e)}})

            # ---- phase 0: RAG 检索 ----
            try:
                if retriever is None:
                    raise RuntimeError("Retriever 不可用（Embedder 或 Milvus 初始化失败）")
                rag_context = retriever.retrieve_as_context(user_query)
                yield sse({"event": "rag_done", "data": {"context_len": len(rag_context)}})
            except Exception as e:
                rag_context = "（RAG 检索不可用，请检查 Milvus 是否启动）"
                logger.bind(task_id=task_id).warning("[rag] 检索失败，降级为空上下文: {}", e)
                yield sse({"event": "rag_done", "data": {"context_len": len(rag_context), "warning": str(e)}})

            # ---- 拼接完整上下文：记忆 + 对话历史 + 参考资料 ----
            history_text = format_history(messages)
            parts = []
            if memory_context:
                parts.append(f"## 历史记忆\n{memory_context}")
            if history_text:
                parts.append(f"## 对话历史\n{history_text}")
            if rag_context:
                parts.append(f"## 参考资料\n{rag_context}")
            full_context = "\n\n".join(parts)

            # ---- phase 1: planning ----
            for event in planner.plan_stream(state, context=full_context):
                yield sse(event)

            # 空计划（闲聊、纯知识问答）：跳过执行+评审，直接结束
            if not state.plan:
                messages.append({"role": "user", "content": user_query})
                messages.append({"role": "assistant", "content": state.thinking})
                redis_client.save_history(session_id, messages)
                _save_episodic_memory(mem_tool, user_query, state.thinking, session_id)
                outcome = "passed_empty_plan"
                yield sse({"event": "done", "data": {"status": "passed", "session_id": session_id}})
                return

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
                    _save_episodic_memory(mem_tool, user_query, state.final_result or state.thinking, session_id)

                    outcome = "passed"
                    yield sse({"event": "done", "data": {"status": "passed", "session_id": session_id}})
                    return

                retry_count += 1
                if retry_count >= MAX_RETRIES:
                    messages.append({"role": "user", "content": user_query})
                    messages.append({"role": "assistant", "content": state.final_result or state.thinking})
                    redis_client.save_history(session_id, messages)
                    _save_episodic_memory(mem_tool, user_query, state.final_result or state.thinking, session_id)

                    outcome = "max_retries"
                    yield sse({"event": "done", "data": {"status": "max_retries", "retry_count": retry_count, "session_id": session_id}})
                    return

                yield sse({"event": "retry", "data": {"retry_count": retry_count}})

        except Exception as e:
            # 友好降级：把异常通过 SSE 告诉前端，而不是直接断连
            outcome = "error"
            logger.bind(task_id=task_id).opt(exception=True).error("[workflow] 流式执行异常")
            yield sse({"event": "error", "data": {"message": f"服务内部异常，请重试。错误: {str(e)}"}})

        finally:
            # ⚠️ 这里只能记日志、绝不能 yield：客户端中途断连时 Starlette 会 close() 生成器，
            #    finally 里 yield 会抛 RuntimeError: generator ignored GeneratorExit。
            #    outcome=aborted 即表示「客户端提前断开」，不是成功。
            logger.bind(request_id=rid, task_id=task_id, session_id=session_id).info(
                "[workflow] done | outcome={} | retry={} | steps={} | elapsed={:.0f}ms",
                outcome, retry_count, len(state.plan) if state else 0,
                (time.perf_counter() - t0) * 1000,
            )

    return StreamingResponse(event_stream(), media_type="text/event-stream")


def _save_episodic_memory(mem_tool, user_query: str, assistant_reply: str, session_id: str):
    """任务结束后自动存为情景记忆（mem_tool 已绑定 user_id）"""
    try:
        mem_tool.memory_manager.add_memory(
            content=f"用户: {user_query}\n助手: {assistant_reply[:500]}",
            memory_type="episodic",
            importance=None,    # ← None 触发 LLM 自评（0.0 ~ 1.0）
            session_id=session_id,
        )

        # 每存 5 条触发一次自动整合
        _maybe_auto_consolidate(mem_tool)
    except Exception as e:
        logger.bind(session_id=session_id).warning("[memory] 自动存情景记忆失败: {}", e)


def _maybe_auto_consolidate(mem_tool, threshold_count: int = 5):
    """每存 N 条 episodic，自动触发一次整合（episodic → semantic）"""
    try:
        count = mem_tool.memory_manager.memory_types.get("episodic")
        if count is None:
            return
        n = count.count()
        if n > 0 and n % threshold_count == 0:
            logger.info("[memory] episodic 达 {} 条，触发自动整合", n)
            mem_tool.memory_manager.consolidate_memories(
                from_type="episodic",
                to_type="semantic",
                importance_threshold=0.7,
            )
    except Exception as e:
        logger.warning("[memory] 自动整合失败: {}", e)


@router.get("/history")
async def get_history(request: Request):
    """获取当前用户的长期记忆历史"""
    user_id = _inject_user(request)
    try:
        mem_tool = _get_memory_tool_for_user(str(user_id))
        items = mem_tool.memory_manager.list_history(top_k=100)
        return JSONResponse({
            "user_id": user_id,
            "count": len(items),
            "items": items,
        })
    except Exception as e:
        return JSONResponse({"error": str(e), "items": []}, status_code=500)


@router.post("/memory/consolidate")
async def consolidate_memory(request: Request):
    """手动触发记忆整合"""
    user_id = _inject_user(request)
    try:
        mem_tool = _get_memory_tool_for_user(str(user_id))
        count = mem_tool.memory_manager.consolidate_memories(
            from_type="episodic",
            to_type="semantic",
            importance_threshold=0.7,
        )
        return JSONResponse({"user_id": user_id, "consolidated": count})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/memory/forget")
async def forget_memory(request: Request):
    """手动触发遗忘机制"""
    user_id = _inject_user(request)
    try:
        mem_tool = _get_memory_tool_for_user(str(user_id))
        count = mem_tool.memory_manager.forget_memories(
            strategy="combined",
            threshold=0.2,
            max_age_days=30,
        )
        return JSONResponse({"user_id": user_id, "forgotten": count})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
