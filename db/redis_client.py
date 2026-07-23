import json
import redis
from config.settings import settings


class RedisClient:
    """会话历史存储 —— 用 session_id 做 key，messages 列表做 value"""

    def __init__(self, host=None, port=None, db=0):
        host = host or settings.REDIS_HOST
        port = port or settings.REDIS_PORT

        self.client = redis.Redis(
            host=host,
            port=port,
            db=db,
            decode_responses=True,
            socket_connect_timeout=3,
        )
        self._available = self._ping()

    def _ping(self) -> bool:
        try:
            self.client.ping()
            print(f"[redis] 已连接 {self.client.connection_pool.connection_kwargs['host']}")
            return True
        except redis.ConnectionError:
            print("[redis] ⚠️  Redis 未启动，多轮对话历史不可用。启动方式：docker-compose up -d redis")
            return False

    @property
    def available(self) -> bool:
        return self._available

    def get_history(self, session_id: str) -> list[dict]:
        if not self._available:
            return []
        try:
            key = f"chat:{session_id}"
            raw = self.client.get(key)
            if raw is None:
                return []
            return json.loads(raw)
        except redis.ConnectionError:
            self._available = False
            print("[redis] ⚠️  连接断开，对话历史不可用")
            return []

    def save_history(self, session_id: str, messages: list[dict], ttl: int = 3600):
        if not self._available:
            return
        try:
            key = f"chat:{session_id}"
            raw = json.dumps(messages, ensure_ascii=False)
            self.client.setex(key, ttl, raw)
        except redis.ConnectionError:
            self._available = False
            print("[redis] ⚠️  连接断开，对话未保存")

    def delete_history(self, session_id: str):
        if not self._available:
            return
        try:
            key = f"chat:{session_id}"
            self.client.delete(key)
        except redis.ConnectionError:
            self._available = False
