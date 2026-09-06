from typing import Optional
from pydantic import BaseModel


class ChatResponse(BaseModel):
    message: str
    session_id: str
    


class TaskResponse(BaseModel):
    task_id: str
    status: str
    result: Optional[dict] = None


class WorkflowResponse(BaseModel):
    workflow_id: str
    status: str
    output: Optional[dict] = None
