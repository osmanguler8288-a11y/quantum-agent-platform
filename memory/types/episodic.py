"""EpisodicMemory — 情景记忆

存放具体事件：「用户在某时刻问了什么、得到什么回答」。
任务结束后自动写入，importance 默认 0.6。
"""

from memory.types.base import BaseMemory


class EpisodicMemory(BaseMemory):
    def __init__(self, config, store, user_id="default_user"):
        super().__init__(config, store, user_id)
        self.memory_type = "episodic"
