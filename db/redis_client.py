import json
import redis
import threading
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
            socket_timeout=3,
        )
        self._available = self._ping()

    def _ping(self) -> bool:
        """带硬超时的 ping：Windows 下 socket_timeout 可能失效，用线程兜底"""
        result = {"ok": False, "err": None}

        def _do():
            try:
                self.client.ping()
                result["ok"] = True
            except Exception as e:
                result["err"] = e

        t = threading.Thread(target=_do, daemon=True)
        t.start()
        t.join(timeout=3)  # 最多等 3 秒

        if t.is_alive() or not result["ok"]:
            if result["err"]:
                print(f"[redis] [WARN] 连接失败: {result['err']}")
            print("[redis] [WARN] Redis 未启动，多轮对话历史不可用。启动方式：docker-compose up -d redis")
            return False

        print(f"[redis] 已连接 {self.client.connection_pool.connection_kwargs['host']}")
        return True

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
        except Exception:
            self._available = False
            print("[redis] [WARN] 连接断开，对话历史不可用")
            return []

    def save_history(self, session_id: str, messages: list[dict], ttl: int = 3600):
        if not self._available:
            return
        try:
            key = f"chat:{session_id}"
            raw = json.dumps(messages, ensure_ascii=False)
            self.client.setex(key, ttl, raw)
        except Exception:
            self._available = False
            print("[redis] [WARN] 连接断开，对话未保存")

    def delete_history(self, session_id: str):
        if not self._available:
            return
        try:
            key = f"chat:{session_id}"
            self.client.delete(key)
        except Exception:
            self._available = False
