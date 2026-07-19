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
        )

    def get_history(self, session_id: str) -> list[dict]:
        """根据 session_id 取出之前的对话，没有就返回空列表"""
        key = f"chat:{session_id}"
        raw = self.client.get(key)
        if raw is None:
            return []
        return json.loads(raw)

    def save_history(self, session_id: str, messages: list[dict], ttl: int = 3600):
        """把对话历史存回 Redis，ttl 秒后自动过期"""
        key = f"chat:{session_id}"
        raw = json.dumps(messages, ensure_ascii=False)
        self.client.setex(key, ttl, raw)

    def delete_history(self, session_id: str):
        """删除某个会话的历史"""
        key = f"chat:{session_id}"
        self.client.delete(key)
