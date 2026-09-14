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
from db.conversation_repo import get_conversation_repo
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


# ─────────────────────────────────────────────────────────────
# 会话落库（唯一入口）
#
# 三条不可动摇的规则，对应方案 §3.2 的边界条件：
#   1. 落库必须发生在**发 done/error 事件之前**。反过来的话前端收到事件就刷新
#      列表，会查不到刚写的这条 —— 竞态，且只在慢磁盘上偶发，极难复现（B7）。
#   2. 落库失败**绝不能**打断对话。用户该拿到的回答一个字都不能少，
#      只是这一轮没持久化（B14）。这与 Redis 时代的降级语义一致。
#   3. 客户端断连时生成器被 close()，抛的是 GeneratorExit（BaseException），
#      `except Exception` 抓不到，只能走 finally 补写（B11）。
#      而 finally 正常路径也会执行，所以必须用 persisted 标志防重（B12）。
# ─────────────────────────────────────────────────────────────
def _ensure_conversation(session_id: str | None, user_id: str) -> tuple[str, bool]:
    """取或建会话，返回 (conversation_id, 是否可落库)。

    DB 不可用时返回一个临时 id 并标记不可落库 —— 对话照常跑，只是不持久化（B41）。
    """
    try:
        return get_conversation_repo().get_or_create(session_id, user_id)["id"], True
    except Exception:
        logger.opt(exception=True).warning(
            "[workflow] 会话存储不可用，本轮对话不落库 session={}", session_id
        )
        return (session_id or str(uuid.uuid4())[:8]), False


def _load_history(conversation_id: str, user_id: str, persisted: bool) -> list[dict]:
    """读历史消息。读失败按「无历史」处理 —— 不能因为读不到历史就不让用户提问。"""
    if not persisted:
        return []
    return get_conversation_repo().get_full_history(conversation_id, user_id)


def _persist_turn(conversation_id: str, user_query: str, reply: str,
                  status: str = "ok", tool_calls: int = 0) -> int:
    """把一轮问答落库，返回实际写入条数（失败返回 0）。**绝不抛异常**（B14）。"""
    try:
        n = get_conversation_repo().append_messages(
            conversation_id,
            [
                {"role": "user", "content": user_query},
                # 空的回复由 repo 跳过（B15），不会留下空气泡
                {"role": "assistant", "content": reply, "status": status},
            ],
            tool_calls=tool_calls,
        )
        logger.info("[workflow] 落库 conv={} 条数={} status={}", conversation_id, n, status)
        return n
    except Exception:
        logger.opt(exception=True).warning(
            "[workflow] 落库失败，本轮未持久化 conv={} status={}", conversation_id, status
        )
        return 0


@router.post("/run")
async def run_workflow(req: WorkflowRequest, request: Request):
    user_id = _inject_user(request)
    task_id = req.workflow_id or str(uuid.uuid4())[:8]
    user_query = req.input_data.get("user_query", "")

    conversation_id, persisted = _ensure_conversation(req.session_id, user_id)

    # 多轮：读历史 + 拼上下文
    messages = _load_history(conversation_id, user_id, persisted)
    history_text = format_history(messages)

    result = app.invoke({
        "task_id": task_id,
        "user_id": user_id,
        "user_query": user_query,
        "current_step": 0,
        "retry_count": 0,
        "history_text": history_text,
    })

    # 多轮：落库（在返回响应之前，保证客户端拿到 session_id 时数据已可见）
    if persisted:
        _persist_turn(conversation_id, user_query, result.get("thinking", ""),
                      tool_calls=len(result.get("results", []) or []))

    # 自动存为情景记忆
    try:
        mem_tool = _get_memory_tool_for_user(str(user_id))
        mem_tool.set_session(conversation_id)
        mem_tool.memory_manager.add_memory(
            content=f"用户: {user_query}\n助手: {result.get('thinking', '')[:500]}",
            memory_type="episodic",
            importance=0.6,
            session_id=conversation_id,
        )
    except Exception as e:
        logger.bind(task_id=task_id).warning("[memory] 自动存记忆失败: {}", e)

    return JSONResponse({
        "task_id": task_id,
        # ⚠️ 新 id 可能与我们收到的不一样（客户端传了别人的/不存在的 id 时会换新，
        #    见 conversation_repo.get_or_create），所以必须回传实际使用的那个（B4）
        "session_id": conversation_id,
        "conversation_id": conversation_id,
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

    # ⚠️ 在**端点体**取会话：客户端传来的 id 可能不存在、甚至属于别人，
    #    get_or_create 会换一个新 id 回来（见 conversation_repo）。之后
    #    所有地方一律用 conversation_id，不再用 req.session_id。
    conversation_id, persisted = _ensure_conversation(req.session_id, user_id)

    # ⚠️ 必须在**端点体**创建（不能放进生成器体内）：这是工具调用埋点能拿到
    #    user/session/task 上下文的唯一时机 —— 生成器跑在线程池，体内 set 的
    #    ContextVar 在下一个 yield 后即失效。详见 app/utils/context.py。
    start_invocation(
        user_id=str(user_id), session_id=conversation_id,
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
        # ⚠️ 落库标志必须装在**可变容器**里：finally 与各正常出口都要读写它，
        #    Python 闭包对不可变类型的赋值只作用于内层作用域。
        turn = {"persisted": False, "count": 0}

        def persist(reply: str, status: str, tool_calls: int = 0) -> None:
            """落库本轮问答（幂等）。**只能在发 done/error 之前调用** —— 见 B7。"""
            if turn["persisted"]:
                return
            turn["persisted"] = True
            if not persisted:
                return
            n = _persist_turn(conversation_id, user_query, reply, status, tool_calls)
            if n:
                turn["count"] += n

        try:
            state = AgentState(task_id=task_id, user_query=user_query)

            # 让前端尽早拿到真实 id —— 可能与它传来的一致，也可能被换过（B4）。
            # 用户在流式过程中刷新页面时，靠它找回这段对话。
            yield sse({"event": "conversation_ready",
                       "data": {"conversation_id": conversation_id}})

            # ---- 为本请求创建专属 MemoryTool（user_id 隔离，避免 thread-local 异步污染）----
            mem_tool = _get_memory_tool_for_user(str(user_id))
            mem_tool.set_session(conversation_id)

            # ---- 取历史（替代原来的 Redis get_history）----
            messages = _load_history(conversation_id, user_id, persisted)
            state.history = messages
            turn["count"] = len(messages)

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
                # ⚠️ persist 必须在 yield done **之前**（B7）：
                #    反过来的话前端收到 done 就刷新列表，会查不到刚写的这条
                persist(state.thinking, "ok")
                _save_episodic_memory(mem_tool, user_query, state.thinking, conversation_id)
                outcome = "passed_empty_plan"
                yield sse({"event": "done", "data": {
                    "status": "passed",
                    "session_id": conversation_id, "conversation_id": conversation_id,
                    "message_count": turn["count"],
                }})
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
                    reply = state.final_result or state.thinking
                    persist(reply, "ok", tool_calls=len(state.results))
                    _save_episodic_memory(mem_tool, user_query, reply, conversation_id)

                    outcome = "passed"
                    yield sse({"event": "done", "data": {
                        "status": "passed",
                        "session_id": conversation_id, "conversation_id": conversation_id,
                        "message_count": turn["count"],
                    }})
                    return

                retry_count += 1
                if retry_count >= MAX_RETRIES:
                    reply = state.final_result or state.thinking
                    # 重试耗尽也是一次「完整的一轮」—— 用户看到了最终答复，
                    # 这轮必须落库，否则刷新后它会凭空消失（B9）
                    persist(reply, "ok", tool_calls=len(state.results))
                    _save_episodic_memory(mem_tool, user_query, reply, conversation_id)

                    outcome = "max_retries"
                    yield sse({"event": "done", "data": {
                        "status": "max_retries", "retry_count": retry_count,
                        "session_id": conversation_id, "conversation_id": conversation_id,
                        "message_count": turn["count"],
                    }})
                    return

                yield sse({"event": "retry", "data": {"retry_count": retry_count}})

        except Exception as e:
            # 友好降级：把异常通过 SSE 告诉前端，而不是直接断连
            outcome = "error"
            logger.bind(task_id=task_id).opt(exception=True).error("[workflow] 流式执行异常")
            # 把**用户已经看到的那部分**存下来 —— 中途报错也让刷新后能复原现场
            persist(state.thinking if state else "", "error")
            yield sse({"event": "error", "data": {
                "message": f"服务内部异常，请重试。错误: {str(e)}",
                "conversation_id": conversation_id,
            }})

        finally:
            # 走到这里还没落过库，只可能是**客户端中途断连**：
            #   close() 在某个 yield 处抛 GeneratorExit，而它继承 BaseException，
            #   上面的 `except Exception` 抓不到 —— 所以补写只能放这里（B11）。
            # 用 status='interrupted' 与正常完成区分开，便于事后判断哪些是半截对话。
            # ⚠️ 这里**只能记日志和写库，绝不能 yield**：生成器已被 close()，
            #    yield 会抛 RuntimeError: generator ignored GeneratorExit（B13）。
            #    outcome=aborted 即表示「客户端提前断开」，不是成功。
            persist(state.thinking if state else "", "interrupted")
            logger.bind(request_id=rid, task_id=task_id, session_id=conversation_id).info(
                "[workflow] done | conv={} | outcome={} | retry={} | steps={} | flagged={} | elapsed={:.0f}ms",
                conversation_id, outcome, retry_count, len(state.plan) if state else 0,
                outcome == "aborted", (time.perf_counter() - t0) * 1000,
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
