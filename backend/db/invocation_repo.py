"""调用埋点的写入与聚合。

设计依据：doc/backdesign/工具库后端设计.md §4（统计）§5（边界条件）

⚠️ 三条硬约束：
    1. 埋点写入**必须独立容错** —— 可观测性不该影响工具可用性（红线 ❌10）。
       DB 挂了，工具照常执行，只是没有统计。
    2. **绝不能**把工具执行包进 DB 事务 —— bash 跑 300s、Gaussian 跑几小时，
       长事务会把整个库锁死（红线 ❌14）。
    3. 无调用记录时 success_rate / avg_duration_ms 返回 None，
       **绝不能返回 NaN** —— 那是非法 JSON，前端解析会崩（红线 ❌11）。
"""
import hashlib
import json
from datetime import datetime, timedelta, timezone

from app.utils.logger import logger
from db.sqlite_client import get_client


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def record_invocation(
    *,
    tool_name: str,
    status: str,
    duration_ms: int | None = None,
    started_at: str | None = None,
    finished_at: str | None = None,
    user_id: str = "default_user",
    session_id: str | None = None,
    task_title: str | None = None,
    step_index: int | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
    params_digest: str | None = None,
) -> int | None:
    """写一条调用记录。返回新 id；失败返回 None（**不抛异常**）。"""
    try:
        client = get_client()
        if not client.available:
            return None
        # 短事务：只包住这一次 INSERT。绝不能把工具执行也包进来（长事务锁库）。
        with client.transaction() as conn:
            tool_id = conn.execute(
                "SELECT id FROM tool WHERE name = ? ORDER BY id LIMIT 1", (tool_name,)
            ).fetchone()
            cur = conn.execute(
                "INSERT INTO tool_invocation (tool_id, tool_name, session_id, user_id, task_title, "
                " step_index, status, error_code, error_message, duration_ms, params_digest, "
                " started_at, finished_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    tool_id[0] if tool_id else None, tool_name, session_id, user_id,
                    (task_title or None) and task_title[:100],
                    step_index, status, error_code,
                    (error_message or None) and error_message[:500],
                    duration_ms, params_digest,
                    started_at or _now(), finished_at or _now(),
                ),
            )
            return cur.lastrowid
    except Exception:
        # ⚠️ 绝不外抛：埋点失败不能影响工具调用
        logger.opt(exception=True).warning("[invocation] 埋点写入失败（不影响本次调用）")
        return None


def params_digest(params: dict) -> str:
    """只存参数指纹，不存全量参数 —— 参数可能含文件路径等敏感信息。"""
    try:
        raw = json.dumps(params, sort_keys=True, ensure_ascii=False, default=str)
    except Exception:
        raw = str(params)
    return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def purge_older_than(days: int = 90) -> int:
    """清理过期埋点。返回删除行数。

    埋点表是唯一会无限增长的表，需要定期清理。由启动钩子调用一次。
    """
    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")
        n = get_client().execute(
            "DELETE FROM tool_invocation WHERE started_at < ?", (cutoff,)
        )
        if n:
            logger.info("[invocation] 清理 {} 天前的埋点 {} 条", days, n)
        return n
    except Exception:
        logger.opt(exception=True).warning("[invocation] 埋点清理失败")
        return 0
