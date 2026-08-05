"""
MilvusStore — 长期记忆的存储层

Collection: agent_memories
字段:
  - vector       (1024 维)
  - text         (记忆内容)
  - user_id      (多用户隔离)
  - memory_type  (working / episodic / semantic / perceptual)
  - importance   (0.0 ~ 1.0)
  - timestamp    (ISO 字符串)
  - session_id   (会话 ID)
  - metadata_json (其余元数据序列化为 JSON 字符串)

与 RAG 的 quantum_docs Collection 隔离，互不干扰。
"""

import json
from datetime import datetime
from typing import Optional

import pymilvus
from pymilvus import MilvusClient as _MilvusClient

from config.settings import settings
from memory.models import MemoryItem, MemoryConfig
from rag.embedder import Embedder


class MilvusStore:
    """记忆存储 — 单独的 Collection，与 RAG 隔离"""

    def __init__(self, config: Optional[MemoryConfig] = None):
        self.config = config or MemoryConfig()
        self.embedder = Embedder()
        self._available = False
        host = settings.MILVUS_HOST
        port = settings.MILVUS_PORT
        uri = f"http://{host}:{port}"

        try:
            self.client = _MilvusClient(uri=uri, timeout=5)
            if not self.client.has_collection(self.config.milvus_collection):
                self._create_collection()
            self.client.load_collection(self.config.milvus_collection)
            self._available = True
            print(f"[memory-store] 已连接 Milvus {host}:{port}, collection={self.config.milvus_collection}")
        except (pymilvus.exceptions.MilvusException, ConnectionError, TimeoutError) as e:
            print(f"[memory-store] [WARN] Milvus 未启动，长期记忆不可用: {e}")

    @property
    def available(self) -> bool:
        return self._available

    def _create_collection(self):
        """创建记忆 Collection（含 metadata 字段）"""
        from pymilvus import CollectionSchema, FieldSchema, DataType

        fields = [
            FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True),
            FieldSchema(name="vector", dtype=DataType.FLOAT_VECTOR, dim=settings.EMBED_DIM),
            FieldSchema(name="text", dtype=DataType.VARCHAR, max_length=40000),
            FieldSchema(name="user_id", dtype=DataType.VARCHAR, max_length=64),
            FieldSchema(name="memory_type", dtype=DataType.VARCHAR, max_length=32),
            FieldSchema(name="importance", dtype=DataType.FLOAT),
            FieldSchema(name="timestamp", dtype=DataType.VARCHAR, max_length=32),
            FieldSchema(name="session_id", dtype=DataType.VARCHAR, max_length=64),
            FieldSchema(name="metadata_json", dtype=DataType.VARCHAR, max_length=8000),
        ]
        schema = CollectionSchema(fields=fields, description="Agent 长期记忆")
        self.client.create_collection(
            collection_name=self.config.milvus_collection,
            schema=schema,
        )

        # 创建向量索引
        index_params = self.client.prepare_index_params()
        index_params.add_index(
            field_name="vector",
            index_type="IVF_FLAT",
            metric_type="COSINE",
            params={"nlist": 128},
        )
        self.client.create_index(
            collection_name=self.config.milvus_collection,
            index_params=index_params,
        )
        print(f"[memory-store] Collection '{self.config.milvus_collection}' 已创建")

    def _embed(self, text: str) -> list[float]:
        return self.embedder.embed_query(text)

    # ─── 写入 ────────────────────────────────────
    def add(self, item: MemoryItem) -> Optional[str]:
        if not self._available:
            return None

        if not item.embedding:
            item.embedding = self._embed(item.content)

        row = {
            "vector": item.embedding,
            "text": item.content[:40000],
            "user_id": item.user_id,
            "memory_type": item.memory_type,
            "importance": float(item.importance),
            "timestamp": item.timestamp.isoformat(),
            "session_id": item.session_id or "",
            "metadata_json": json.dumps(item.metadata, ensure_ascii=False)[:8000],
        }
        result = self.client.insert(self.config.milvus_collection, [row])
        ids = result.get("ids") if isinstance(result, dict) else None
        if ids:
            item.id = str(ids[0])
        print(f"[memory-store] 写入记忆 user={item.user_id} type={item.memory_type} importance={item.importance:.2f}")
        return item.id

    # ─── 搜索 ────────────────────────────────────
    def search(
        self,
        query: str,
        user_id: str,
        memory_types: Optional[list[str]] = None,
        min_importance: float = 0.1,
        top_k: int = 5,
    ) -> list[MemoryItem]:
        if not self._available:
            return []

        vec = self._embed(query)
        if not vec:
            return []

        # 构造过滤表达式（多用户隔离 + 类型筛选 + 重要性阈值）
        expr_parts = [f'user_id == "{user_id}"', f'importance >= {float(min_importance)}']
        if memory_types:
            types_str = ", ".join([f'"{t}"' for t in memory_types])
            expr_parts.append(f'memory_type in [{types_str}]')
        expr = " && ".join(expr_parts)

        try:
            results = self.client.search(
                collection_name=self.config.milvus_collection,
                data=[vec],
                limit=top_k,
                filter=expr,
                output_fields=["text", "user_id", "memory_type", "importance", "timestamp", "session_id", "metadata_json"],
            )
        except Exception as e:
            print(f"[memory-store] 搜索失败: {e}")
            return []

        hits = results[0] if results else []
        items: list[MemoryItem] = []
        for hit in hits:
            ent = hit.get("entity", {}) if isinstance(hit, dict) else {}
            items.append(MemoryItem(
                id=str(hit.get("id", "")),
                user_id=ent.get("user_id", user_id),
                memory_type=ent.get("memory_type", "unknown"),
                content=ent.get("text", ""),
                importance=float(ent.get("importance", 0.0)),
                timestamp=self._parse_dt(ent.get("timestamp")),
                session_id=ent.get("session_id") or None,
                metadata=self._parse_meta(ent.get("metadata_json")),
                score=hit.get("distance", 0.0),
            ))
        return items

    # ─── 按条件查询（不向量化） ────────────────────
    def query(
        self,
        user_id: str,
        memory_type: Optional[str] = None,
        session_id: Optional[str] = None,
        order_by_importance: bool = True,
        top_k: int = 50,
    ) -> list[MemoryItem]:
        """按 metadata 查询（不走向量搜索），用于历史记录浏览"""
        if not self._available:
            return []

        expr_parts = [f'user_id == "{user_id}"']
        if memory_type:
            expr_parts.append(f'memory_type == "{memory_type}"')
        if session_id:
            expr_parts.append(f'session_id == "{session_id}"')
        expr = " && ".join(expr_parts)

        try:
            results = self.client.query(
                collection_name=self.config.milvus_collection,
                filter=expr,
                output_fields=["text", "user_id", "memory_type", "importance", "timestamp", "session_id", "metadata_json"],
                limit=top_k,
            )
        except Exception as e:
            print(f"[memory-store] query 失败: {e}")
            return []

        items = []
        for ent in results:
            items.append(MemoryItem(
                id=str(ent.get("id", "")) if "id" in ent else None,
                user_id=ent.get("user_id", user_id),
                memory_type=ent.get("memory_type", "unknown"),
                content=ent.get("text", ""),
                importance=float(ent.get("importance", 0.0)),
                timestamp=self._parse_dt(ent.get("timestamp")),
                session_id=ent.get("session_id") or None,
                metadata=self._parse_meta(ent.get("metadata_json")),
            ))
        if order_by_importance:
            items.sort(key=lambda x: x.importance, reverse=True)
        return items

    # ─── 更新重要性（整合用） ────────────────────────
    def update_importance(self, item_id: str, new_importance: float):
        """通过先删后插实现 update（Milvus 不支持原地更新）"""
        if not self._available:
            return
        try:
            self.client.delete(self.config.milvus_collection, filter=f'id in [{item_id}]')
            print(f"[memory-store] 已删除记忆 {item_id}（重要性更新前清理）")
        except Exception as e:
            print(f"[memory-store] 更新重要性失败: {e}")

    # ─── 删除 ────────────────────────────────────
    def delete_by_filter(self, expr: str) -> int:
        """按表达式批量删除（遗忘机制用）"""
        if not self._available:
            return 0
        try:
            result = self.client.query(
                collection_name=self.config.milvus_collection,
                filter=expr,
                output_fields=["id"],
                limit=10000,
            )
            ids = [r.get("id") for r in result if r.get("id") is not None]
            if not ids:
                return 0
            ids_str = ", ".join(str(i) for i in ids)
            self.client.delete(self.config.milvus_collection, filter=f'id in [{ids_str}]')
            print(f"[memory-store] 删除 {len(ids)} 条记忆 (filter={expr})")
            return len(ids)
        except Exception as e:
            print(f"[memory-store] 删除失败: {e}")
            return 0

    # ─── 工具方法 ────────────────────────────────
    @staticmethod
    def _parse_dt(s) -> datetime:
        if not s:
            return datetime.now()
        try:
            return datetime.fromisoformat(s)
        except Exception:
            return datetime.now()

    @staticmethod
    def _parse_meta(s):
        if not s:
            return {}
        try:
            return json.loads(s)
        except Exception:
            return {}
