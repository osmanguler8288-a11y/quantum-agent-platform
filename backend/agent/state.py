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
    def __init__(self, task_id: str, user_query: str = ""):
        self.task_id = task_id
        self.status = TaskStatus.PENDING
        self.thinking: str = ""
        self.plan: list[dict] = []
        self.current_step = 0
        self.results: list[dict] = []
        self.retry_count = 0
        self.user_query = user_query
        self.final_result: str = ""
        self.history: list[dict] = []  # 用于存储对话历史，方便在执行过程中参考



    def transition(self, new_status: TaskStatus):
        old = self.status
        self.status = new_status
        print(f"[state] {old.value} → {new_status.value}")

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "user_query": self.user_query,
            "status": self.status.value,
            "plan": self.plan,
            "current_step": self.current_step,
            "total_steps": len(self.plan),
            "results": self.results,
            "thinking": self.thinking,
            "retry_count": self.retry_count,
            "final_result": self.final_result,
        }
