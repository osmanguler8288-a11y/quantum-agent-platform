class MilvusDBClient:
    def __init__(self, host: str = "localhost", port: int = 19530):
        self.host = host
        self.port = port

    def create_collection(self, name: str, dim: int):
        pass

    def search(self, collection: str, vector: list[float], top_k: int = 10) -> list[dict]:
        return []

    def insert(self, collection: str, vectors: list[list[float]], metadata: list[dict]):
        pass
