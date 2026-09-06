"""
MemoryTool — 把 MemoryManager 包装成 Agent 工具

让 Planner 可以通过工具调用，主动记忆和检索长期记忆。
"""

from datetime import datetime
from typing import List, Optional

from memory.manager import MemoryManager
from memory.models import MemoryConfig


class MemoryTool:
    """记忆工具 — 让 Agent 主动存/取/整合/遗忘长期记忆"""

    def __init__(
        self,
        user_id: str = "default_user",
        memory_config: Optional[MemoryConfig] = None,
        memory_types: List[str] = None,
        llm=None,
    ):
        if memory_types is None:
            memory_types = ["working", "episodic", "semantic"]

        self.memory_manager = MemoryManager(
            config=memory_config,
            user_id=user_id,
            llm=llm,
            enable_working="working" in memory_types,
            enable_episodic="episodic" in memory_types,
            enable_semantic="semantic" in memory_types,
            enable_perceptual="perceptual" in memory_types,
        )
        self.current_session_id: Optional[str] = None

    def set_session(self, session_id: str):
        self.current_session_id = session_id

    # ─── 添加记忆 ────────────────────────────────
    def add(
        self,
        content: str = "",
        memory_type: str = "working",
        importance: float = None,
        **metadata,
    ) -> str:
        try:
            if self.current_session_id and "session_id" not in metadata:
                metadata["session_id"] = self.current_session_id

            memory_id = self.memory_manager.add_memory(
                content=content,
                memory_type=memory_type,
                importance=importance,
                **metadata,
            )
            return f"已添加记忆 (type={memory_type}, id={memory_id[:8] if memory_id else 'N/A'})"
        except Exception as e:
            return f"添加记忆失败: {e}"

    # ─── 搜索记忆 ────────────────────────────────
    def search(
        self,
        query: str,
        limit: int = 5,
        memory_type: str = None,
        memory_types: List[str] = None,
        min_importance: float = 0.1,
    ) -> str:
        try:
            if memory_type and not memory_types:
                memory_types = [memory_type]

            results = self.memory_manager.retrieve_memories(
                query=query,
                limit=limit,
                memory_types=memory_types,
                min_importance=min_importance,
            )

            if not results:
                return f"未找到与 '{query}' 相关的记忆"

            type_labels = {
                "working": "工作", "episodic": "情景",
                "semantic": "语义", "perceptual": "感知",
            }
            lines = [f"找到 {len(results)} 条相关记忆:"]
            for i, mem in enumerate(results, 1):
                label = type_labels.get(mem.memory_type, mem.memory_type)
                preview = mem.content[:80] + "..." if len(mem.content) > 80 else mem.content
                score = mem.score or 0.0
                lines.append(f"{i}. [{label}/{mem.importance:.2f}/score={score:.3f}] {preview}")
            return "\n".join(lines)
        except Exception as e:
            return f"搜索记忆失败: {e}"

    # ─── 整合记忆 ────────────────────────────────
    def consolidate(
        self,
        from_type: str = "working",
        to_type: str = "semantic",
        importance_threshold: float = 0.7,
    ) -> str:
        try:
            count = self.memory_manager.consolidate_memories(
                from_type=from_type,
                to_type=to_type,
                importance_threshold=importance_threshold,
            )
            return f"已整合 {count} 条 {from_type} → {to_type} 记忆 (阈值={importance_threshold})"
        except Exception as e:
            return f"整合记忆失败: {e}"

    # ─── 遗忘记忆 ────────────────────────────────
    def forget(
        self,
        strategy: str = "importance_based",
        threshold: float = 0.1,
        max_age_days: int = 30,
    ) -> str:
        try:
            count = self.memory_manager.forget_memories(
                strategy=strategy,
                threshold=threshold,
                max_age_days=max_age_days,
            )
            return f"已遗忘 {count} 条记忆 (策略: {strategy})"
        except Exception as e:
            return f"遗忘记忆失败: {e}"

    # ─── 列出历史记忆 ────────────────────────────
    def history(self, top_k: int = 20) -> str:
        try:
            items = self.memory_manager.list_history(top_k=top_k)
            if not items:
                return "暂无历史记忆"
            lines = [f"共 {len(items)} 条历史记忆:"]
            for i, item in enumerate(items, 1):
                lines.append(
                    f"{i}. [{item['type']}/{item['importance']:.2f}] {item['content'][:100]}"
                )
            return "\n".join(lines)
        except Exception as e:
            return f"获取历史失败: {e}"
