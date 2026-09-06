import json as json_module
import uuid
from fastapi import APIRouter
from fastapi.responses import StreamingResponse, JSONResponse
from app.schemas.request import ChatRequest
from app.schemas.response import ChatResponse
from llm.client import LLMClient
from db.redis_client import RedisClient

router = APIRouter()

llm = LLMClient()
redis_client = RedisClient()


def sse(event: str, data: dict | str) -> str:
    """SSE 格式化"""
    payload = data if isinstance(data, str) else json_module.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"


@router.post("/", response_model=ChatResponse)
async def chat(req: ChatRequest):
    session_id = req.session_id or str(uuid.uuid4())[:8]
    messages = redis_client.get_history(session_id)
    messages.append({"role": "user", "content": req.message})
    reply = llm.console(messages)
    messages.append({"role": "assistant", "content": reply})
    redis_client.save_history(session_id, messages)
    return ChatResponse(message=reply, session_id=session_id)



@router.post("/stream")
async def chat_stream(req: ChatRequest):
    session_id = req.session_id or str(uuid.uuid4())[:8]
    messages = redis_client.get_history(session_id)
    messages.append({"role": "user", "content": req.message})

    def event_stream():
        full_reply = ""
        try:
            for token in llm.console_stream(messages):
                full_reply += token
                yield sse("token", token)
            messages.append({"role": "assistant", "content": full_reply})
            redis_client.save_history(session_id, messages)
            yield sse("done", {"session_id": session_id})
        except Exception as e:
            yield sse("error", {"message": f"对话出错: {str(e)}"})

    return StreamingResponse(event_stream(), media_type="text/event-stream")
   