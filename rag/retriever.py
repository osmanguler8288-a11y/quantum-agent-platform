from rag.embedder import Embedder
from rag.vector_db import MilvusClient


class Retriever:
    def __init__(self, embedder: Embedder, vector_db: MilvusClient):
        self.embedder = embedder
        self.vector_db = vector_db

    def retrieve(self, query: str, top_k: int = 5) -> list[dict]:
        """Retrieve relevant documents for a query."""
        query_embedding = self.embedder.embed_query(query)
        return self.vector_db.search(query_embedding, top_k)

    def retrieve_as_context(self, query: str, top_k: int = 5) -> str:
        """
        检索并拼成一段可直接注入 prompt 的上下文。
        Agent 用这个方法把 RAG 结果塞进 Planner 的 system prompt。
        """
        results = self.retrieve(query, top_k)
        if not results:
            return "（未找到相关资料）"

        parts = []
        for i, r in enumerate(results):
            parts.append(
                f"[参考资料 {i + 1}] (相关度: {r['score']:.2f})\n{r['text']}"
            )
        return "\n\n---\n\n".join(parts)
