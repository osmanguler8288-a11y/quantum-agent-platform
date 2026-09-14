"""SQLite 客户端 —— 工具库元数据与调用埋点的存储。

风格对齐 db/redis_client.py：构造内探活、`_available` 降级标志、每个方法首行短路、
失败只记日志不抛异常。

⚠️ 四条 SQLite 特有的硬约束（都是实测踩出来的）：
    1. `sqlite3.threadsafety == 1` —— 连接**不能跨线程共享**。FastAPI 的 sync 端点与
       SSE 生成器都在 anyio 线程池里跑，所以必须用 thread-local 连接
       （这样 check_same_thread 保持默认 True 最安全，不需要传 False）。
    2. `PRAGMA foreign_keys` 默认 **OFF** —— 不开则 ON DELETE SET NULL / CASCADE 全部失效，
       必须在**每个新建连接**上设置（不是一次性）。
    3. 「先读后写」必须 `BEGIN IMMEDIATE` —— 默认的 deferred 事务遇到锁升级时
       **不受 busy_timeout 保护**，直接抛 "database is locked"。
    4. `PRAGMA journal_mode=WAL` 是写进文件头、持久化的，设一次即可。
"""
import os
import sqlite3
import threading
from contextlib import contextmanager

from config.settings import settings
from app.utils.logger import logger
from db.schema import SCHEMA_VERSION, apply_schema, current_version


class SQLiteClient:
    """线程安全的 SQLite 客户端（thread-local 连接）。"""

    def __init__(self, path: str | None = None):
        self.path = path or settings.SQLITE_PATH
        self._local = threading.local()
        self._available = False
        self._bootstrap()

    # ─── 初始化 ──────────────────────────────────────
    def _bootstrap(self) -> None:
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            conn = self._conn()          # 首次建连接（会设置 pragma + 建表）
            apply_schema(conn)
            ver = current_version(conn)
            if ver < SCHEMA_VERSION:
                conn.execute(
                    "INSERT OR REPLACE INTO schema_version(version, applied_at) VALUES (?, ?)",
                    (SCHEMA_VERSION, _now()),
                )
                conn.commit()
            self._available = True
            logger.info("[sqlite] 已就绪 path={} schema_version={}", self.path, SCHEMA_VERSION)
        except Exception:
            # 与 redis_client 一致：连不上只降级，不阻止应用启动
            logger.opt(exception=True).warning(
                "[sqlite] 初始化失败，工具库元数据不可用 path={}", self.path
            )
            self._available = False

    def _conn(self) -> sqlite3.Connection:
        """拿到当前线程的连接，没有就建一个并设 pragma。"""
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self.path, timeout=5.0)
            conn.row_factory = sqlite3.Row
            # ⚠️ 逐连接 pragma：foreign_keys 默认 OFF，不开外键约束等于没有
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA busy_timeout = 5000")
            conn.execute("PRAGMA synchronous = NORMAL")
            # WAL 持久化在文件头，重复设幂等；首次设置若被其他连接占用会失败，可忽略
            try:
                conn.execute("PRAGMA journal_mode = WAL")
            except sqlite3.OperationalError as e:
                logger.warning("[sqlite] 开启 WAL 失败（不影响使用）: {}", e)
            self._local.conn = conn
        return conn

    # ─── 状态 ────────────────────────────────────────
    @property
    def available(self) -> bool:
        return self._available

    def _degrade(self, exc: Exception) -> None:
        self._available = False
        logger.warning("[sqlite] 连接异常，工具库元数据降级不可用: {}", exc)

    # ─── 查询 ────────────────────────────────────────
    def query(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        if not self._available:
            return []
        try:
            return self._conn().execute(sql, params).fetchall()
        except Exception as e:
            self._degrade(e)
            return []

    def query_one(self, sql: str, params: tuple = ()) -> sqlite3.Row | None:
        if not self._available:
            return None
        try:
            return self._conn().execute(sql, params).fetchone()
        except Exception as e:
            self._degrade(e)
            return None

    def scalar(self, sql: str, params: tuple = (), default=None):
        row = self.query_one(sql, params)
        return row[0] if row is not None else default

    # ─── 写入 ────────────────────────────────────────
    def execute(self, sql: str, params: tuple = ()) -> int:
        """执行单条写语句，返回 rowcount。失败返回 0。"""
        if not self._available:
            return 0
        try:
            conn = self._conn()
            cur = conn.execute(sql, params)
            conn.commit()
            return cur.rowcount
        except Exception as e:
            self._degrade(e)
            return 0

    @contextmanager
    def transaction(self):
        """事务上下文：读-改-写序列必须用它。

        ⚠️ 用 BEGIN IMMEDIATE 而非默认的 deferred：deferred 事务在「先读后写」
           时会发生锁升级，而**锁升级不受 busy_timeout 保护**，直接抛 database is locked。
        ⚠️ 绝不要在这里面执行工具（子进程/网络调用），会长时间锁库。
        """
        if not self._available:
            raise DBUnavailable(self.path)
        conn = self._conn()
        conn.execute("BEGIN IMMEDIATE")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def healthcheck(self) -> dict:
        """健康检查：供 /api/health 使用。"""
        if not self._available:
            return {"available": False, "path": self.path}
        try:
            n = self.scalar("SELECT COUNT(*) FROM tool WHERE deleted_at IS NULL", default=0)
            return {
                "available": True,
                "path": self.path,
                "tools": n,
                "schema_version": current_version(self._conn()),
                "journal_mode": self.scalar("PRAGMA journal_mode"),
            }
        except Exception as e:
            return {"available": False, "path": self.path, "error": str(e)}


class DBUnavailable(RuntimeError):
    """数据库不可用（由路由层转成 503 DB_UNAVAILABLE）。"""


class NullSQLiteClient:
    """数据库不可用时的空对象：查询返回空，写入抛 DBUnavailable。

    与 NullRedis 同一个思路 —— 路由层不必到处判 None。
    """

    available = False
    path = ""

    def query(self, sql, params=()):
        return []

    def query_one(self, sql, params=()):
        return None

    def scalar(self, sql, params=(), default=None):
        return default

    def execute(self, sql, params=()):
        return 0

    @contextmanager
    def transaction(self):
        raise DBUnavailable("SQLite 不可用")
        yield  # pragma: no cover

    def healthcheck(self):
        return {"available": False, "path": self.path}


# ─── 单例 ────────────────────────────────────────────
_client: SQLiteClient | NullSQLiteClient | None = None
_lock = threading.Lock()


def get_client():
    """懒加载单例。首次调用时建库建表。"""
    global _client
    if _client is None:
        with _lock:
            if _client is None:
                try:
                    _client = SQLiteClient()
                except Exception:
                    logger.opt(exception=True).error("[sqlite] 客户端构造失败，降级为空实现")
                    _client = NullSQLiteClient()
    return _client


def reset_client() -> None:
    """测试用：清掉单例。"""
    global _client
    with _lock:
        _client = None


def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
