"""BaseMemory — 记忆类型的抽象基类"""

from datetime import datetime
from typing import Optional

from memory.models import MemoryItem, MemoryConfig
from memory.store import MilvusStore


class BaseMemory:
    """所有记忆类型的基类，提供 add / retrieve / delete 通用方法"""

    def __init__(self, config: MemoryConfig, store: MilvusStore, user_id: str = "default_user"):
        self.config = config
        self.store = store
        self.user_id = user_id
        # 子类必须覆盖
        self.memory_type: str = "base"

    def add(self, content: str, importance: float = 0.5,
            session_id: Optional[str] = None, **metadata) -> Optional[str]:
        """添加一条记忆"""
        item = MemoryItem(
            user_id=self.user_id,
            memory_type=self.memory_type,
            content=content,
            importance=float(importance),
            timestamp=datetime.now(),
            session_id=session_id,
            metadata=metadata,
        )
        return self.store.add(item)

    def retrieve(self, query: str, limit: int = 5) -> list[MemoryItem]:
        """检索记忆（按 memory_type 自动过滤）"""
        return self.store.search(
            query=query,
            user_id=self.user_id,
            memory_types=[self.memory_type],
            top_k=limit,
        )

    def list_all(self, top_k: int = 100) -> list[MemoryItem]:
        """列出该类型所有记忆（按重要性排序）"""
        return self.store.query(
            user_id=self.user_id,
            memory_type=self.memory_type,
            top_k=top_k,
        )

    def count(self) -> int:
        """统计数量"""
        return len(self.list_all(top_k=10000))
