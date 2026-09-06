from fastapi import APIRouter

router = APIRouter()


@router.get("/ping")
async def server_status():
    return {"pong": True, "time": "2024-01-01"}
