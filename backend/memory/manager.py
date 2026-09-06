"""
MemoryManager — 记忆模块统一入口

组装 Store + Retriever + 四种记忆类型，提供 add/retrieve/consolidate/forget 接口。
"""

from typing import Optional

from memory.models import MemoryConfig
from memory.store import MilvusStore
from memory.retriever import MemoryRetriever
from memory.types import WorkingMemory, EpisodicMemory, SemanticMemory, PerceptualMemory


class MemoryManager:
    """记忆管理器 — 统一的记忆操作接口"""

    def __init__(
        self,
        config: Optional[MemoryConfig] = None,
        user_id: str = "default_user",
        llm=None,
        enable_working: bool = True,
        enable_episodic: bool = True,
        enable_semantic: bool = True,
        enable_perceptual: bool = False,
    ):
        self.config = config or MemoryConfig()
        self.user_id = user_id
        self.llm = llm

        # 共享 Store + Retriever
        self.store = MilvusStore(self.config)
        self.retriever = MemoryRetriever(self.store, self.config, llm=llm)

        # 初始化各类型记忆
        self.memory_types = {}
        if enable_working:
            self.memory_types["working"] = WorkingMemory(self.config, self.store, user_id)
        if enable_episodic:
            self.memory_types["episodic"] = EpisodicMemory(self.config, self.store, user_id)
        if enable_semantic:
            self.memory_types["semantic"] = SemanticMemory(self.config, self.store, user_id)
        if enable_perceptual:
            self.memory_types["perceptual"] = PerceptualMemory(self.config, self.store, user_id)

    # ─── 添加记忆 ────────────────────────────────
    def add_memory(
        self,
        content: str,
        memory_type: str = "working",
        importance: float = None,    # None → 触发自评
        auto_classify: bool = False,
        **metadata,
    ) -> str:
        # 找到对应类型
        mem = self.memory_types.get(memory_type)
        if not mem:
            return None

        # 重要性自评
        if importance is None:
            importance = self.retriever.evaluate_importance(content, self.user_id)

        memory_id = mem.add(content, importance=importance, **metadata)
        return memory_id

    # ─── 检索记忆 ────────────────────────────────
    def retrieve_memories(
        self,
        query: str,
        limit: int = 5,
        memory_types: Optional[list[str]] = None,
        min_importance: float = 0.1,
    ):
        return self.retriever.retrieve(
            query=query,
            user_id=self.user_id,
            memory_types=memory_types,
            min_importance=min_importance,
            limit=limit,
        )

    # ─── 整合记忆 ────────────────────────────────
    def consolidate_memories(
        self,
        from_type: str = "working",
        to_type: str = "semantic",
        importance_threshold: float = None,
    ) -> int:
        threshold = importance_threshold if importance_threshold is not None else self.config.consolidate_threshold
        return self.retriever.consolidate(
            user_id=self.user_id,
            from_types=[from_type],
            importance_threshold=threshold,
        )

    # ─── 遗忘记忆 ────────────────────────────────
    def forget_memories(
        self,
        strategy: str = "importance_based",
        threshold: float = None,
        max_age_days: int = None,
    ) -> int:
        return self.retriever.forget(
            user_id=self.user_id,
            strategy=strategy,
            threshold=threshold,
            max_age_days=max_age_days,
        )

    # ─── 列出所有记忆（用于历史展示）────────────────
    def list_history(self, top_k: int = 50) -> list[dict]:
        items = self.store.query(user_id=self.user_id, top_k=top_k)
        # 按 timestamp 升序返回（旧→新）
        items.sort(key=lambda x: x.timestamp)
        return [
            {
                "id": i.id,
                "type": i.memory_type,
                "content": i.content,
                "importance": i.importance,
                "timestamp": i.timestamp.isoformat(),
                "session_id": i.session_id,
            }
            for i in items
        ]
