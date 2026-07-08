from typing import Optional
from pydantic import BaseModel


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None


class TaskRequest(BaseModel):
    task_type: str
    params: dict = {}


class WorkflowRequest(BaseModel):
    workflow_id: str
    input_data: dict = {}
