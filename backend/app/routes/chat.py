"""简易对话接口（裸 LLM，非 Agent 链路）。

⚠️ **前端不走这里** —— 前端用的是 `/api/workflow/stream` 的完整 Agent 流程
   （规划 → 执行 → 评审）。本模块保留给脚本 / 调试场景：想直接跟模型聊两句、
   不启动工具链时用。

历史存储已从 Redis 迁到 SQLite，与 Agent 链路**同源** —— 也就是说
从这儿聊的内容和从对话界面聊的内容落在同一张 conversation 表里，
用同一个 conversation id 续接。Redis 至此完全退出对话链路。
"""
import json as json_module
import uuid

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse, JSONResponse
from app.schemas.request import ChatRequest
from app.schemas.response import ChatResponse
from app.utils.logger import logger
from llm.client import LLMClient
from db.conversation_repo import get_conversation_repo

router = APIRouter()


def _safe_llm():
    """⚠️ 与 workflow.py 同一个理由：模块级单例构造失败会让整个应用起不来。
    LLM_API_KEY 为空时 openai SDK 构造即抛 —— 应当降级而不是阻止启动。"""
    try:
        return LLMClient()
    except Exception:
        logger.opt(exception=True).error("[chat] LLMClient 初始化失败，/api/chat 不可用")
        return None


llm = _safe_llm()


def _inject_user(request: Request) -> str:
    """与 workflow/conversations 同一来源：Go 网关注入的 X-User-ID。"""
    return request.headers.get("X-User-ID") or "default_user"


def _session(req: ChatRequest, user_id: str) -> tuple[str, bool]:
    """取或建会话，返回 (conversation_id, 是否可落库)。DB 不可用时降级为空实现。"""
    try:
        return get_conversation_repo().get_or_create(req.session_id, user_id)["id"], True
    except Exception:
        logger.opt(exception=True).warning("[chat] 会话存储不可用，本轮不落库")
        return (req.session_id or str(uuid.uuid4())[:12]), False


def _history(conversation_id: str, user_id: str, persisted: bool) -> list[dict]:
    return get_conversation_repo().get_full_history(conversation_id, user_id) if persisted else []


def _persist(conversation_id: str, user_message: str, reply: str, status: str = "ok") -> None:
    """落库一轮问答。**绝不抛异常** —— 存不上不能把回复吞掉。"""
    try:
        get_conversation_repo().append_messages(conversation_id, [
            {"role": "user", "content": user_message},
            {"role": "assistant", "content": reply, "status": status},
        ])
    except Exception:
        logger.opt(exception=True).warning("[chat] 落库失败 conv={}", conversation_id)


def sse(event: str, data: dict | str) -> str:
    """SSE 格式化"""
    payload = data if isinstance(data, str) else json_module.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"


@router.post("/", response_model=ChatResponse)
async def chat(req: ChatRequest, request: Request):
    if llm is None:
        return JSONResponse({"error": "LLM 不可用（未配置 API Key）", "code": "LLM_UNAVAILABLE"},
                            status_code=503)

    user_id = _inject_user(request)
    conversation_id, persisted = _session(req, user_id)

    messages = _history(conversation_id, user_id, persisted)
    messages.append({"role": "user", "content": req.message})
    reply = llm.console(messages)

    if persisted:
        _persist(conversation_id, req.message, reply)

    return ChatResponse(message=reply, session_id=conversation_id)


@router.post("/stream")
async def chat_stream(req: ChatRequest, request: Request):
    if llm is None:
        return JSONResponse({"error": "LLM 不可用（未配置 API Key）", "code": "LLM_UNAVAILABLE"},
                            status_code=503)

    user_id = _inject_user(request)
    conversation_id, persisted = _session(req, user_id)

    messages = _history(conversation_id, user_id, persisted)
    messages.append({"role": "user", "content": req.message})

    def event_stream():
        full_reply = ""
        try:
            for token in llm.console_stream(messages):
                full_reply += token
                yield sse("token", token)
        except Exception as e:
            logger.opt(exception=True).error("[chat] 流式对话异常 conv={}", conversation_id)
            # 与 workflow 一致：已生成的部分也存下来，刷新后还能看到
            if persisted:
                _persist(conversation_id, req.message, full_reply, status="error")
            yield sse("error", {"message": f"对话出错: {str(e)}"})
            return

        # ⚠️ 先落库再发 done：反过来的话客户端收到 done 立刻刷新，会查不到刚写的这条
        if persisted:
            _persist(conversation_id, req.message, full_reply)
        yield sse("done", {"session_id": conversation_id, "conversation_id": conversation_id})

    return StreamingResponse(event_stream(), media_type="text/event-stream")
