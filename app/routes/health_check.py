from fastapi import APIRouter

router = APIRouter()


@router.get("/server")
async def server_status():
    return {"server": "running", "version": "1.0.0"}
