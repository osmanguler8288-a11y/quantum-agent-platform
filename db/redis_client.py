class RedisClient:
    def __init__(self, host: str = "localhost", port: int = 6379, db: int = 0):
        self.host = host
        self.port = port
        self.db = db

    def get(self, key: str) -> str | None:
        return None

    def set(self, key: str, value: str, ttl: int = 3600):
        pass

    def delete(self, key: str):
        pass
