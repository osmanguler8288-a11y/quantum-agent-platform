"""
MemoryRetriever — 记忆检索 + 高级特性

四项高级能力：
  1. 时效衰减：score *= 0.5 ** (age_days / half_life)，新记忆权重更高
  2. 自动整合（consolidate）：高重要性 working/episodic → LLM 抽取共性 → 写入 semantic
  3. 遗忘（forget）：低重要性 或 老旧记忆 → 删除
  4. 重要性自评（evaluate_importance）：写入前让 LLM 给重要性打分（0~1）
"""

import json
import math
from datetime import datetime
from typing import Optional

from memory.models import MemoryItem, MemoryConfig
from memory.store import MilvusStore


class MemoryRetriever:
    def __init__(self, store: MilvusStore, config: Optional[MemoryConfig] = None, llm=None):
        self.store = store
        self.config = config or MemoryConfig()
        self.llm = llm   # 重要性自评和整合时用

    # ─── 检索（带时效衰减）────────────────────────────
    def retrieve(
        self,
        query: str,
        user_id: str,
        memory_types: Optional[list[str]] = None,
        min_importance: float = 0.1,
        limit: int = 5,
    ) -> list[MemoryItem]:
        items = self.store.search(
            query=query,
            user_id=user_id,
            memory_types=memory_types,
            min_importance=min_importance,
            top_k=limit * 2,    # 多取一些用于衰减后重排
        )
        # 时效衰减
        for item in items:
            item.score = (item.score or 0.0) * self._decay_factor(item.timestamp)
        items.sort(key=lambda x: x.score or 0.0, reverse=True)
        return items[:limit]

    def _decay_factor(self, ts: datetime) -> float:
        age_days = max(0.0, (datetime.now() - ts).total_seconds() / 86400)
        return 0.5 ** (age_days / self.config.decay_half_life_days)

    # ─── 重要性自评 ─────────────────────────────────
    def evaluate_importance(self, content: str, user_id: str) -> float:
        """让 LLM 给内容打分（0.0 ~ 1.0），失败时返回 0.5 兜底"""
        if not self.llm or not self.config.enable_importance_self_eval:
            return 0.5

        prompt = f"""请评估下面这条记忆对该用户的重要性，返回 0.0 到 1.0 之间的浮点数。

评分标准:
- 1.0: 包含关键偏好、长期有效规则、核心技术信息（如「用户偏好 B3LYP 泛函」）
- 0.7: 重要的事实或事件，可能复用（如「上次苯的优化结果」）
- 0.4: 一般性对话内容
- 0.2: 闲聊、问候、临时性问题

仅返回一个浮点数，不要其他文字。

用户 ID: {user_id}
记忆内容: {content[:500]}"""
        try:
            raw = self.llm.generate(prompt).strip()
            # 提取第一个浮点数
            for token in raw.replace("\n", " ").split():
                try:
                    val = float(token)
                    return max(0.0, min(1.0, val))
                except ValueError:
                    continue
            return 0.5
        except Exception as e:
            print(f"[memory] 重要性自评失败: {e}")
            return 0.5

    # ─── 自动整合（working/episodic → semantic）──────
    def consolidate(
        self,
        user_id: str,
        from_types: Optional[list[str]] = None,
        importance_threshold: Optional[float] = None,
    ) -> int:
        """把高重要性的 working/episodic 记忆整合成 semantic 知识"""
        if not self.llm:
            print("[memory] 跳过整合：未注入 LLM")
            return 0

        from_types = from_types or ["working", "episodic"]
        threshold = importance_threshold if importance_threshold is not None else self.config.consolidate_threshold

        # 1. 拉取高重要性记忆
        items = self.store.query(user_id=user_id, top_k=1000)
        candidates = [i for i in items if i.memory_type in from_types and i.importance >= threshold]
        if not candidates:
            print(f"[memory] 无高重要性记忆可整合 (threshold={threshold})")
            return 0

        # 2. 让 LLM 抽取共性，写成 1 条 semantic 记忆
        candidates_text = "\n".join([f"- [{i.memory_type}/{i.importance:.2f}] {i.content[:200]}" for i in candidates[:20]])
        prompt = f"""你是记忆整合器。下面是用户的多条历史记忆，请抽取共性、规律、偏好，写成 1~3 条简洁的语义知识。

要求:
1. 输出 JSON 数组，每个元素: {{"content": "...", "importance": 0.x}}
2. 知识必须从给定记忆中归纳出来，不能编造
3. 重要性根据覆盖范围给分（多条记忆都体现的偏好 → 0.9）

用户 ID: {user_id}
候选记忆:
{candidates_text}

输出 JSON:"""

        try:
            raw = self.llm.generate(prompt)
            # 解析 JSON
            start = raw.rfind("[")
            if start == -1:
                return 0
            end = raw.rfind("]") + 1
            knowledge_list = json.loads(raw[start:end])
        except Exception as e:
            print(f"[memory] 整合 LLM 解析失败: {e}")
            return 0

        # 3. 写入 semantic 记忆
        count = 0
        for k in knowledge_list:
            if not isinstance(k, dict) or "content" not in k:
                continue
            item = MemoryItem(
                user_id=user_id,
                memory_type="semantic",
                content=k["content"],
                importance=float(k.get("importance", 0.8)),
                timestamp=datetime.now(),
                metadata={"consolidated_from": ",".join(from_types)},
            )
            self.store.add(item)
            count += 1

        print(f"[memory] 整合出 {count} 条 semantic 记忆 (源: {len(candidates)} 条)")
        return count

    # ─── 遗忘机制 ────────────────────────────────
    def forget(
        self,
        user_id: str,
        strategy: str = "importance_based",
        threshold: Optional[float] = None,
        max_age_days: Optional[int] = None,
    ) -> int:
        """按策略删除记忆"""
        threshold = threshold if threshold is not None else self.config.forget_threshold
        max_age_days = max_age_days or self.config.max_age_days

        # 先拉所有记忆，按策略筛选要删的 ID
        all_items = self.store.query(user_id=user_id, top_k=10000)
        to_delete_ids: list[int] = []

        now = datetime.now()
        for item in all_items:
            should_delete = False
            if strategy == "importance_based":
                if item.importance < threshold:
                    should_delete = True
            elif strategy == "age_based":
                age_days = (now - item.timestamp).days
                if age_days > max_age_days:
                    should_delete = True
            elif strategy == "lru":
                # 最久未访问：直接用 timestamp 排序末尾 N 条
                pass
            elif strategy == "combined":
                # 低重要性 AND 老旧 → 删
                age_days = (now - item.timestamp).days
                if item.importance < threshold and age_days > max_age_days / 2:
                    should_delete = True

            if should_delete and item.id:
                try:
                    to_delete_ids.append(int(item.id))
                except (ValueError, TypeError):
                    continue

        if not to_delete_ids:
            return 0

        ids_str = ", ".join(str(i) for i in to_delete_ids)
        return self.store.delete_by_filter(f'id in [{ids_str}]')
