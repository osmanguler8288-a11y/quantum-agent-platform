from enum import Enum


class TaskStatus(str, Enum):
    PENDING = "pending"
    PLANNING = "planning"
    EXECUTING = "executing"
    REVIEWING = "reviewing"
    RETRYING = "retrying"
    DONE = "done"
    FAILED = "failed"


class AgentState:
    def __init__(self, task_id: str):
        self.task_id = task_id
        self.status = TaskStatus.PENDING
        self.plan: list[dict] = []
        self.current_step = 0
        self.results: list[dict] = []
        self.retry_count = 0

    def transition(self, new_status: TaskStatus):
        self.status = new_status

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "status": self.status.value,
            "current_step": self.current_step,
            "retry_count": self.retry_count,
        }
