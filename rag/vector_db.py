import pymilvus
from pymilvus import MilvusClient as _MilvusClient
from config.settings import settings

# BGE-large-zh-v1.5 输出 1024 维
VECTOR_DIM = settings.EMBED_DIM
COLLECTION_NAME = "quantum_docs"


class MilvusClient:
    """Milvus 向量数据库客户端 — 存向量 + 搜相似（pymilvus 3.0 新 API）"""

    def __init__(self, host: str = None, port: int = None):
        host = host or settings.MILVUS_HOST
        port = port or settings.MILVUS_PORT
        uri = f"http://{host}:{port}"

        self._available = False
        try:
            self.client = _MilvusClient(uri=uri, timeout=5)

            if not self.client.has_collection(COLLECTION_NAME):
                self._create_collection()

            self.client.load_collection(COLLECTION_NAME)
            self._available = True
            print(f"[milvus] 已连接 {host}:{port}")
        except (pymilvus.exceptions.MilvusException, ConnectionError, TimeoutError) as e:
            print(f"[milvus] ⚠️  Milvus 未启动，RAG 检索不可用。启动方式：docker-compose up -d standalone")
            print(f"[milvus]  原因: {e}")

    @property
    def available(self) -> bool:
        return self._available

    # ─── 创建表结构 ───
    def _create_collection(self):
        self.client.create_collection(
            collection_name=COLLECTION_NAME,
            dimension=VECTOR_DIM,
            metric_type="COSINE",
            auto_id=True,                    # 自动生成主键
            schema_fields=[
                {"name": "text", "type": "VARCHAR", "max_length": 40000},
                {"name": "source", "type": "VARCHAR", "max_length": 256},
                {"name": "chunk_idx", "type": "INT64"},
            ],
        )
        print(f"[milvus] Collection '{COLLECTION_NAME}' 已创建")

    # ─── 写入向量 ───
    def insert(self, vectors: list[list[float]], metadata: list[dict]):
        if not vectors or not self._available:
            return

        rows = []
        for vec, meta in zip(vectors, metadata):
            rows.append({
                "vector": vec,
                "text": meta.get("text", ""),
                "source": meta.get("source", ""),
                "chunk_idx": meta.get("chunk_idx", 0),
            })

        self.client.insert(COLLECTION_NAME, rows)
        print(f"[milvus] 写入 {len(rows)} 条向量")

    # ─── 搜索最相似的向量 ───
    def search(self, vector: list[float], top_k: int = 5) -> list[dict]:
        if not self._available:
            return []

        results = self.client.search(
            collection_name=COLLECTION_NAME,
            data=[vector],
            limit=top_k,
            output_fields=["text", "source", "chunk_idx"],
        )

        hits = results[0]
        return [
            {
                "text": hit["entity"].get("text"),
                "source": hit["entity"].get("source"),
                "chunk_idx": hit["entity"].get("chunk_idx"),
                "score": hit["distance"],
            }
            for hit in hits
        ]
