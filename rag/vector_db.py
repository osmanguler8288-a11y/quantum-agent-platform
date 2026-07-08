class MilvusClient:
    def __init__(self, host: str = "localhost", port: int = 19530):
        self.host = host
        self.port = port

    def search(self, vector: list[float], top_k: int = 5) -> list[dict]:
        """Search for similar vectors."""
        return []

    def insert(self, vectors: list[list[float]], metadata: list[dict]):
        """Insert vectors with metadata."""
        pass
