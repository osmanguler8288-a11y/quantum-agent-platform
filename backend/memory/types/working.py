"""WorkingMemory — 短期工作记忆

存放当前会话的临时上下文：用户最近问题、助手最近回复。
TTL 短，重要性低，很快被遗忘或升级为 episodic。
"""

from memory.types.base import BaseMemory


class WorkingMemory(BaseMemory):
    def __init__(self, config, store, user_id="default_user"):
        super().__init__(config, store, user_id)
        self.memory_type = "working"
