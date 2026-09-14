import json
import redis
import threading
from config.settings import settings
from app.utils.logger import logger


class RedisClient:
    """⚠️ **已废弃** —— 会话历史不再存 Redis。

    为什么弃用（见 doc/对话存储-SQLite可行性报告.md §9.2）：

        1. **没有 user_id**。key 只有 `chat:{session_id}`，无法回答「这段对话属于谁」，
           多用户隔离根本无从谈起。
        2. **没有时间戳**。列表页要的「最近活动时间」「会话顺序」全都推导不出来。
        3. **TTL 会过期**。`save_history` 默认 3600s —— 用户一小时后回来，
           历史已经永久消失，且没有任何办法恢复。
        4. **读全量→改→写全量**。并发下两个请求互相覆盖，**静默丢消息**，
           连报错都没有。

    现役实现在 [db/conversation_repo.py](backend/db/conversation_repo.py)：
    一个库文件 + user_id 列 + 只追加写 + 唯一约束兜底。

    本类保留仅为兼容历史代码，**新代码不要再调用**。
    """

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
                logger.warning("[redis] 连接失败: {}", result["err"])
            logger.warning("[redis] Redis 未启动，多轮对话历史不可用。启动方式：docker-compose up -d redis")
            return False

        logger.info("[redis] 已连接 {}", self.client.connection_pool.connection_kwargs['host'])
        return True

    @property
    def available(self) -> bool:
        return self._available

    def get_history(self, session_id: str) -> list[dict]:
        """@deprecated 用 ConversationRepository.get_full_history() 代替。"""
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
            logger.warning("[redis] 连接断开，对话历史不可用")
            return []

    def save_history(self, session_id: str, messages: list[dict], ttl: int = 3600):
        """@deprecated 用 ConversationRepository.append_messages() 代替。

        ⚠️ 后者是**只追加**语义 —— 本方法的「写全量」在并发下会互相覆盖，
           这正是弃用它的主要原因之一。
        """
        if not self._available:
            return
        try:
            key = f"chat:{session_id}"
            raw = json.dumps(messages, ensure_ascii=False)
            self.client.setex(key, ttl, raw)
        except Exception:
            self._available = False
            logger.warning("[redis] 连接断开，对话未保存")

    def delete_history(self, session_id: str):
        if not self._available:
            return
        try:
            key = f"chat:{session_id}"
            self.client.delete(key)
        except Exception:
            self._available = False


class NullRedis:
    """Redis 完全不可用时的空对象。

    历史上 workflow.py 里有多处**直接**调用它（外面没有 try/except），
    为 None 会直接 AttributeError 把整条对话链路打断 —— 所以用空对象兜住。

    ⚠️ 现状：对话链路已全部迁到 SQLite，**没有任何模块再实例化 RedisClient**，
       因此本类目前是闲置的。保留它是为了「将来 Redis 只做缓存」时
       仍然有现成的降级范式可复用（SQLite 侧的对应物是 NullSQLiteClient）。
    """

    available = False

    def get_history(self, session_id: str) -> list[dict]:
        return []

    def save_history(self, session_id: str, messages: list[dict], ttl: int = 3600):
        return None

    def delete_history(self, session_id: str):
        return None
