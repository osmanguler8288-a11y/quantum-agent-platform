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
