from pydantic import BaseModel
from datetime import datetime


class TaskRecord(BaseModel):
    task_id: str
    task_type: str
    status: str
    created_at: datetime
    completed_at: datetime | None = None
    result: dict | None = None


class DocumentRecord(BaseModel):
    doc_id: str
    source: str
    chunk_count: int
    ingested_at: datetime
