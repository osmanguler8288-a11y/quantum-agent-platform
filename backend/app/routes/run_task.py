from fastapi import APIRouter

router = APIRouter()


@router.post("/")
async def run_task():
    return {"message": "run task endpoint"}
