class Embedder:
    def __init__(self, model_name: str = "text-embedding-3-small"):
        self.model_name = model_name

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for a list of texts."""
        return [[0.0] * 1536 for _ in texts]

    def embed_query(self, query: str) -> list[float]:
        """Generate embedding for a single query."""
        return [0.0] * 1536
