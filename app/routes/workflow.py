from fastapi import APIRouter

router = APIRouter()


@router.post("/")
async def trigger_workflow():
    return {"message": "workflow endpoint"}
