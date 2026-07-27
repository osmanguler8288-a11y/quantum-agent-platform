"""
MemoryTool — 为 Agent 提供记忆功能

将 MemoryManager 包装为 Agent 可调用的标准工具，支持记忆的增删查改和整合。
"""

from datetime import datetime
from typing import List, Optional

from memory.manager import MemoryManager


class MemoryTool:
    """记忆工具 — 存储和检索对话历史、知识和经验"""

    def __init__(
        self,
        user_id: str = "default_user",
        memory_config=None,
        memory_types: List[str] = None,
    ):
        if memory_types is None:
            memory_types = ["working", "episodic", "semantic"]

        self.memory_manager = MemoryManager(
            config=memory_config,
            user_id=user_id,
            enable_working="working" in memory_types,
            enable_episodic="episodic" in memory_types,
            enable_semantic="semantic" in memory_types,
            enable_perceptual="perceptual" in memory_types,
        )
        self.current_session_id: Optional[str] = None

    # ─── 添加记忆 ────────────────────────────────

    def add(
        self,
        content: str = "",
        memory_type: str = "working",
        importance: float = 0.5,
        file_path: str = None,
        modality: str = None,
        **metadata,
    ) -> str:
        """添加一条新记忆。

        Args:
            content:      记忆内容文本
            memory_type:  记忆类型（working / episodic / semantic / perceptual）
            importance:   重要性权重（0.0 ~ 1.0）
            file_path:    关联文件路径（感知记忆）
            modality:     感知模态（text / image / audio），可由文件路径自动推断

        Returns:
            操作结果描述
        """
        try:
            if self.current_session_id is None:
                self.current_session_id = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

            # 感知记忆：自动推断模态
            if memory_type == "perceptual" and file_path:
                inferred = modality or self._infer_modality(file_path)
                metadata.setdefault("modality", inferred)
                metadata.setdefault("raw_data", file_path)

            metadata.update({
                "session_id": self.current_session_id,
                "timestamp": datetime.now().isoformat(),
            })

            memory_id = self.memory_manager.add_memory(
                content=content,
                memory_type=memory_type,
                importance=importance,
                metadata=metadata,
                auto_classify=False,
            )

            return f"✅ 记忆已添加 (ID: {memory_id[:8]}...)"

        except Exception as e:
            return f"❌ 添加记忆失败: {e}"

    # ─── 搜索记忆 ────────────────────────────────

    def search(
        self,
        query: str,
        limit: int = 5,
        memory_types: List[str] = None,
        memory_type: str = None,
        min_importance: float = 0.1,
    ) -> str:
        """搜索记忆。

        Args:
            query:          搜索查询文本
            limit:          最大返回条数
            memory_types:   限定搜索的记忆类型列表
            memory_type:    单个记忆类型（与 memory_types 二选一）
            min_importance: 最低重要性阈值

        Returns:
            格式化搜索结果
        """
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
                return f"🔍 未找到与 '{query}' 相关的记忆"

            type_labels = {
                "working": "工作记忆",
                "episodic": "情景记忆",
                "semantic": "语义记忆",
                "perceptual": "感知记忆",
            }

            lines = [f"🔍 找到 {len(results)} 条相关记忆:"]
            for i, mem in enumerate(results, 1):
                label = type_labels.get(mem.memory_type, mem.memory_type)
                preview = mem.content[:80] + "..." if len(mem.content) > 80 else mem.content
                lines.append(
                    f"{i}. [{label}] {preview} (重要性: {mem.importance:.2f})"
                )

            return "\n".join(lines)

        except Exception as e:
            return f"❌ 搜索记忆失败: {e}"

    # ─── 整合记忆 ────────────────────────────────

    def consolidate(
        self,
        from_type: str = "working",
        to_type: str = "episodic",
        importance_threshold: float = 0.7,
    ) -> str:
        """将重要的短期记忆提升为长期记忆。

        Args:
            from_type:            来源记忆类型
            to_type:              目标记忆类型
            importance_threshold: 重要性阈值，高于此值的记忆被提升

        Returns:
            操作结果描述
        """
        try:
            count = self.memory_manager.consolidate_memories(
                from_type=from_type,
                to_type=to_type,
                importance_threshold=importance_threshold,
            )
            return (
                f"🔄 已整合 {count} 条记忆为长期记忆"
                f"（{from_type} → {to_type}，阈值={importance_threshold}）"
            )
        except Exception as e:
            return f"❌ 整合记忆失败: {e}"

    # ─── 遗忘记忆 ────────────────────────────────

    def forget(
        self,
        strategy: str = "importance_based",
        threshold: float = 0.1,
        max_age_days: int = 30,
    ) -> str:
        """根据策略遗忘/清理记忆。

        Args:
            strategy:     遗忘策略（importance_based / age_based / lru）
            threshold:    重要性阈值，低于此值的记忆被遗忘
            max_age_days: 最大保留天数（age_based 策略）

        Returns:
            操作结果描述
        """
        try:
            count = self.memory_manager.forget_memories(
                strategy=strategy,
                threshold=threshold,
                max_age_days=max_age_days,
            )
            return f"🧹 已遗忘 {count} 条记忆（策略: {strategy}）"
        except Exception as e:
            return f"❌ 遗忘记忆失败: {e}"

    # ─── 辅助方法 ────────────────────────────────

    @staticmethod
    def _infer_modality(file_path: str) -> str:
        """根据文件扩展名推断感知模态。"""
        ext = file_path.lower().rsplit(".", 1)[-1] if "." in file_path else ""
        mapping = {
            "png": "image", "jpg": "image", "jpeg": "image",
            "wav": "audio", "mp3": "audio",
            "txt": "text", "md": "text", "pdf": "text",
        }
        return mapping.get(ext, "unknown")
