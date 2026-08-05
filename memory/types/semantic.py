"""SemanticMemory — 语义记忆

存放抽象知识：用户偏好、规则、共性问题。
来源：
  1. 用户主动 add（type=semantic）
  2. 自动整合：working/episodic 中 importance > 阈值的记忆，LLM 抽取共性后写入
"""

from memory.types.base import BaseMemory


class SemanticMemory(BaseMemory):
    def __init__(self, config, store, user_id="default_user"):
        super().__init__(config, store, user_id)
        self.memory_type = "semantic"
