from fastapi import APIRouter
from app.schemas.request import ChatRequest
from app.schemas.response import ChatResponse
from llm.client import LLMClient
from config.settings import settings

router = APIRouter()


@router.post("/", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """接收用户消息，返回回复"""
    client = LLMClient(
        api_key=settings.LLM_API_KEY,
        model=settings.LLM_MODEL,
        base_url=settings.LLM_BASE_URL,
    )
    reply = client.generate(req.message)
    return ChatResponse(message=reply, session_id=req.session_id or "default")
