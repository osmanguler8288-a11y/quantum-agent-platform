import hashlib
import json


class RedisCache:
    def __init__(self, host: str = "localhost", port: int = 6379):
        self.host = host
        self.port = port

    def get(self, key: str) -> str | None:
        return None

    def set(self, key: str, value: str, ttl: int = 3600):
        pass

    def make_key(self, prompt: str, model: str) -> str:
        raw = json.dumps({"prompt": prompt, "model": model}, sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()
