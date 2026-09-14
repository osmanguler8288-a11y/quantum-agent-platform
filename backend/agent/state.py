import time
from enum import Enum

from app.utils.logger import logger


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

        # 计时基准：用于记录各状态停留时长与任务累计时长
        self._t_created = time.perf_counter()
        self._t_last_transition = self._t_created

    def transition(self, new_status: TaskStatus):
        """状态迁移 —— 任务生命周期的唯一观测点。

        记录三段信息：迁移前后状态、上一状态停留时长、任务累计时长。
        「停留时长」是定位瓶颈的关键：planning 停留久 = LLM 慢，
        executing 停留久 = 工具慢。
        """
        old = self.status
        now = time.perf_counter()
        dwell_ms = (now - self._t_last_transition) * 1000
        total_ms = (now - self._t_created) * 1000
        self._t_last_transition = now
        self.status = new_status

        logger.bind(task_id=self.task_id).info(
            "[state] {} → {} | 停留={:.0f}ms 累计={:.0f}ms",
            old.value, new_status.value, dwell_ms, total_ms,
        )

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
