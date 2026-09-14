"""工具元数据仓储层 —— tool / tool_category / tool_tag / tool_audit_log 的唯一写入者。

设计依据：doc/backdesign/工具库后端设计.md §4

约定：
    - 所有 SQL 一律参数化（? 占位符），**禁止字符串拼接**
    - LIKE 查询必须转义 % 和 _，否则 keyword="%" 会匹配全部
    - 读-改-写序列走 client.transaction()（BEGIN IMMEDIATE）
    - 返回给上层的都是普通 dict / list，不暴露 sqlite3.Row
"""
import json
import re
import threading
from datetime import datetime, timezone

from app.utils.logger import logger
from db.sqlite_client import get_client

# 恢复窗口：删除后 N 天内可恢复
RESTORE_WINDOW_DAYS = 7

# 工具名规范：与现有 17 个内置工具命名一致（小写 + 下划线，字母开头）
NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")

_VALID_SOURCES = ("builtin", "mcp")
_VALID_STATUS = ("enabled", "disabled")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _esc_like(s: str) -> str:
    """转义 LIKE 通配符。

    ⚠️ 不转义时 keyword="%" 会匹配所有记录，"_" 会匹配任意单字符 —— 搜索结果静默出错。
       配合 SQL 里的 `ESCAPE '\\'` 使用。
    """
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _loads(raw, fallback):
    """带兜底的反序列化 —— 坏数据不能让整个接口 500。"""
    if raw is None or raw == "":
        return fallback
    try:
        return json.loads(raw)
    except Exception:
        return fallback


class ToolRepository:
    """工具元数据 CRUD。"""

    def __init__(self, client=None):
        self.client = client or get_client()

    # ══════════════════════════════════════════════════
    # 读
    # ══════════════════════════════════════════════════
    def list_tools(self, keyword=None, category=None, status=None, source=None,
                   page=1, page_size=9, include_deleted=False) -> dict:
        """列表查询。

        返回 {"items", "total"(筛选后), "enabled_count"(全量未筛选)}。
        ⚠️ total 与 enabled_count 语义不同，前者对应「共 N 条」，后者对应「已启用 N 个」。
        """
        where, params = [], []

        if not include_deleted:
            where.append("t.deleted_at IS NULL")
        if status in ("enabled", "disabled"):
            where.append("t.status = ?")
            params.append(status)
        if source in _VALID_SOURCES:
            where.append("t.source = ?")
            params.append(source)
        if category:
            where.append("c.name = ?")
            params.append(category)

        keyword = (keyword or "").strip()
        if keyword:
            like = f"%{_esc_like(keyword)}%"
            where.append(
                "(t.name LIKE ? ESCAPE '\\' OR t.display_name LIKE ? ESCAPE '\\' "
                " OR t.user_description LIKE ? ESCAPE '\\' "
                " OR EXISTS (SELECT 1 FROM tool_tag g WHERE g.tool_id = t.id "
                "            AND g.tag_name LIKE ? ESCAPE '\\'))"
            )
            params.extend([like, like, like, like])

        where_sql = ("WHERE " + " AND ".join(where)) if where else ""

        total = self.client.scalar(
            f"SELECT COUNT(*) FROM tool t JOIN tool_category c ON c.id = t.category_id {where_sql}",
            tuple(params), default=0,
        )
        enabled_count = self.client.scalar(
            "SELECT COUNT(*) FROM tool WHERE deleted_at IS NULL AND status = 'enabled'",
            default=0,
        )

        offset = (page - 1) * page_size
        rows = self.client.query(
            f"SELECT t.*, c.name AS category FROM tool t "
            f"JOIN tool_category c ON c.id = t.category_id "
            f"{where_sql} ORDER BY t.sort_order, t.id LIMIT ? OFFSET ?",
            (*params, page_size, offset),
        )
        items = [self._row_to_dict(r) for r in rows]
        self._attach_tags(items)
        return {"items": items, "total": total, "enabled_count": enabled_count}

    def get_tool(self, tool_id: int, *, include_deleted=False, with_stats=False,
                 invocation_limit: int = 5) -> dict | None:
        row = self.client.query_one(
            "SELECT t.*, c.name AS category FROM tool t "
            "JOIN tool_category c ON c.id = t.category_id WHERE t.id = ?",
            (tool_id,),
        )
        if row is None:
            return None
        if row["deleted_at"] and not include_deleted:
            return None

        item = self._row_to_dict(row)
        self._attach_tags([item])
        item["param_rows"] = self._param_rows(item["parameters"])

        if with_stats:
            item["stats"] = self.get_stats(tool_id, tool_name=item["name"])
            item["recent_invocations"] = self.list_invocations(
                tool_id, page=1, page_size=max(0, min(invocation_limit, 50))
            )["items"]
        return item

    def list_categories(self) -> dict:
        """分类及计数（只统计未删除的工具）。"""
        rows = self.client.query(
            "SELECT c.id, c.name, c.is_builtin, COUNT(t.id) AS count "
            "FROM tool_category c "
            "LEFT JOIN tool t ON t.category_id = c.id AND t.deleted_at IS NULL "
            "GROUP BY c.id, c.name, c.is_builtin ORDER BY c.sort_order, c.id"
        )
        items = [
            {"id": r["id"], "name": r["name"],
             "is_builtin": bool(r["is_builtin"]), "count": r["count"]}
            for r in rows
        ]
        total = self.client.scalar(
            "SELECT COUNT(*) FROM tool WHERE deleted_at IS NULL", default=0
        )
        return {"items": items, "total": total}

    def list_enabled_for_agent(self) -> list[dict]:
        """registry 重建用：只返回「启用且未删除」的工具。"""
        rows = self.client.query(
            "SELECT name, source, endpoint, llm_description, parameters "
            "FROM tool WHERE deleted_at IS NULL AND status = 'enabled' "
            "ORDER BY sort_order, id"
        )
        return [dict(r) for r in rows]

    def resolve_id_by_name(self, name: str) -> int | None:
        return self.client.scalar(
            "SELECT id FROM tool WHERE name = ? AND deleted_at IS NULL", (name,)
        )

    # ══════════════════════════════════════════════════
    # 写
    # ══════════════════════════════════════════════════
    def create_tool(self, payload: dict, operator: str = "default_user") -> int:
        """新增工具，返回新 id。唯一性冲突由调用方先查（DB 层有部分唯一索引兜底）。"""
        now = _now()
        tags = payload.get("tags") or []
        with self.client.transaction() as conn:
            cur = conn.execute(
                "INSERT INTO tool (name, display_name, category_id, source, status, endpoint, "
                " icon, user_description, llm_description, parameters, param_template, "
                " is_destructive, sort_order, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    payload["name"],
                    payload["display_name"],
                    payload["category_id"],
                    payload["source"],
                    payload.get("status", "enabled"),
                    payload.get("endpoint"),
                    payload.get("icon") or "🔧",
                    payload.get("user_description", ""),
                    payload.get("llm_description") or payload.get("user_description", ""),
                    json.dumps(payload.get("parameters") or {}, ensure_ascii=False),
                    json.dumps(payload.get("param_template") or {}, ensure_ascii=False),
                    1 if payload.get("is_destructive") else 0,
                    payload.get("sort_order", 200),
                    now, now,
                ),
            )
            tool_id = cur.lastrowid
            self._replace_tags(conn, tool_id, tags)
            self._audit(conn, tool_id, payload["name"], "create",
                        {"after": {"display_name": payload["display_name"],
                                   "source": payload["source"]}}, operator)
        logger.info("[tools] 新增工具 id={} name={} source={}",
                    tool_id, payload["name"], payload["source"])
        return tool_id

    def update_tool(self, tool_id: int, payload: dict,
                    operator: str = "default_user") -> dict | None:
        """更新工具。只更新 payload 里出现的字段（部分更新）。

        ⚠️ 契约字段（name/source/endpoint/parameters/llm_description）对内置工具的
           可改性由**路由层**校验，仓储层只负责写。
        """
        before_row = self.client.query_one("SELECT * FROM tool WHERE id = ?", (tool_id,))
        if before_row is None:
            return None
        before = dict(before_row)

        updatable = {
            "display_name", "category_id", "status", "endpoint", "icon",
            "user_description", "llm_description", "is_destructive", "sort_order",
        }
        sets, params = [], []
        for field in updatable:
            if field in payload and payload[field] is not None:
                sets.append(f"{field} = ?")
                params.append(1 if field == "is_destructive" and payload[field] else payload[field])

        for field in ("parameters", "param_template"):
            if field in payload and payload[field] is not None:
                sets.append(f"{field} = ?")
                params.append(json.dumps(payload[field], ensure_ascii=False))

        now = _now()
        sets.append("updated_at = ?")
        params.append(now)
        params.append(tool_id)

        with self.client.transaction() as conn:
            conn.execute(f"UPDATE tool SET {', '.join(sets)} WHERE id = ?", tuple(params))
            if "tags" in payload and payload["tags"] is not None:
                self._replace_tags(conn, tool_id, payload["tags"])
            self._audit(conn, tool_id, before["name"], "update",
                        {"before": {k: before.get(k) for k in payload if k in updatable},
                         "after": {k: v for k, v in payload.items() if k in updatable}},
                        operator)

        logger.info("[tools] 更新工具 id={} name={} 字段={}", tool_id, before["name"], sorted(payload))
        return self.get_tool(tool_id, include_deleted=True)

    def set_status(self, tool_id: int, status: str,
                   operator: str = "default_user") -> dict | None:
        """启停。幂等：设为当前值不报错。"""
        row = self.client.query_one("SELECT name, status FROM tool WHERE id = ? AND deleted_at IS NULL", (tool_id,))
        if row is None:
            return None
        if row["status"] == status:
            return {"id": tool_id, "name": row["name"], "status": status, "changed": False}

        now = _now()
        with self.client.transaction() as conn:
            conn.execute("UPDATE tool SET status = ?, updated_at = ? WHERE id = ?",
                         (status, now, tool_id))
            self._audit(conn, tool_id, row["name"],
                        "enable" if status == "enabled" else "disable", None, operator)
        logger.info("[tools] {} 工具 id={} name={}", "启用" if status == "enabled" else "停用",
                    tool_id, row["name"])
        return {"id": tool_id, "name": row["name"], "status": status, "changed": True}

    def soft_delete(self, tool_id: int, operator: str = "default_user") -> dict | None:
        """软删除（写 deleted_at）。调用方需先校验 source != builtin。"""
        row = self.client.query_one("SELECT name, deleted_at FROM tool WHERE id = ?", (tool_id,))
        if row is None:
            return None
        if row["deleted_at"]:
            raise AlreadyDeleted(tool_id)

        now = _now()
        with self.client.transaction() as conn:
            conn.execute("UPDATE tool SET deleted_at = ?, updated_at = ? WHERE id = ?",
                         (now, now, tool_id))
            self._audit(conn, tool_id, row["name"], "delete", None, operator)
        logger.warning("[tools] 软删除工具 id={} name={} operator={}", tool_id, row["name"], operator)
        return {"id": tool_id, "name": row["name"], "deleted_at": now,
                "restorable_until": _plus_days(now, RESTORE_WINDOW_DAYS)}

    def restore(self, tool_id: int, operator: str = "default_user") -> dict | None:
        """恢复软删的工具。超过恢复窗口抛 RestoreWindowExpired。"""
        row = self.client.query_one("SELECT name, deleted_at, status FROM tool WHERE id = ?", (tool_id,))
        if row is None:
            return None
        if not row["deleted_at"]:
            raise NotDeleted(tool_id)
        if _days_since(row["deleted_at"]) > RESTORE_WINDOW_DAYS:
            raise RestoreWindowExpired(tool_id, row["deleted_at"])

        now = _now()
        with self.client.transaction() as conn:
            conn.execute("UPDATE tool SET deleted_at = NULL, updated_at = ? WHERE id = ?",
                         (now, tool_id))
            self._audit(conn, tool_id, row["name"], "restore", None, operator)
        # 恢复后保持删除前的 status（status 与 deleted_at 正交）
        logger.info("[tools] 恢复工具 id={} name={} status={}", tool_id, row["name"], row["status"])
        return {"id": tool_id, "name": row["name"], "status": row["status"], "deleted_at": None}

    # ══════════════════════════════════════════════════
    # 统计
    # ══════════════════════════════════════════════════
    def get_stats(self, tool_id: int, tool_name: str | None = None) -> dict:
        """详情页四宫格数据。

        ⚠️ 无调用记录时 success_rate / avg_duration_ms 必须返回 None（前端显示「—」），
           **绝不能返回 NaN** —— 那是非法 JSON，前端解析会崩。
        """
        row = self.client.query_one(
            "SELECT COUNT(*) AS total, "
            "       SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) AS ok, "
            "       AVG(duration_ms) AS avg_ms, "
            "       MAX(started_at) AS last_at "
            "FROM tool_invocation WHERE tool_id = ?",
            (tool_id,),
        )
        total = (row["total"] or 0) if row else 0

        name = tool_name or self.client.scalar("SELECT name FROM tool WHERE id = ?", (tool_id,))
        since = _days_ago(30)
        recent_30d = self.client.scalar(
            "SELECT COUNT(*) FROM tool_invocation WHERE tool_name = ? AND started_at >= ?",
            (name, since), default=0,
        ) if name else 0

        return {
            "total_invocations": total,
            "success_rate": round((row["ok"] or 0) / total, 4) if total else None,
            "avg_duration_ms": round(row["avg_ms"]) if total and row["avg_ms"] is not None else None,
            "last_invoked_at": row["last_at"] if row else None,
            "recent_30d_invocations": recent_30d,
        }

    def list_invocations(self, tool_id: int, page: int = 1, page_size: int = 20,
                         status: str | None = None) -> dict:
        where = ["tool_id = ?"]
        params: list = [tool_id]
        if status in ("success", "error"):
            where.append("status = ?")
            params.append(status)
        where_sql = "WHERE " + " AND ".join(where)

        total = self.client.scalar(
            f"SELECT COUNT(*) FROM tool_invocation {where_sql}", tuple(params), default=0
        )
        rows = self.client.query(
            f"SELECT id, tool_name, session_id, task_title, step_index, status, "
            f"       error_code, error_message, duration_ms, started_at, finished_at "
            f"FROM tool_invocation {where_sql} ORDER BY started_at DESC, id DESC LIMIT ? OFFSET ?",
            (*params, page_size, (page - 1) * page_size),
        )
        return {"items": [dict(r) for r in rows], "total": total}

    # ══════════════════════════════════════════════════
    # 内部
    # ══════════════════════════════════════════════════
    def _row_to_dict(self, row) -> dict:
        d = dict(row)
        d["parameters"] = _loads(d.get("parameters"), {})
        d["param_template"] = _loads(d.get("param_template"), {})
        d["is_destructive"] = bool(d.get("is_destructive"))
        d["deleted"] = d.get("deleted_at") is not None
        d["tags"] = []
        d["capabilities"] = self._capabilities(d)
        # 派生：调用统计（列表页「调用 1,284 次」）
        inline = self.client.query_one(
            "SELECT COUNT(*) AS n, MAX(started_at) AS last_at FROM tool_invocation WHERE tool_id = ?",
            (d["id"],),
        )
        d["invocation_count"] = (inline["n"] or 0) if inline else 0
        d["last_invoked_at"] = inline["last_at"] if inline else None
        return d

    @staticmethod
    def _capabilities(d: dict) -> dict:
        """把 D3 规则显式暴露给前端，避免前端硬编码「内置不可删」。

        前端应依据 can_delete 决定是否渲染删除按钮。
        """
        is_builtin = d.get("source") == "builtin"
        deleted = d.get("deleted", False)
        return {
            "can_edit": not deleted,
            "can_delete": (not is_builtin) and (not deleted),
            "can_disable": not deleted,
            "can_restore": deleted,
            "delete_blocked_reason": (
                "内置工具不可删除，如需停用请使用启停开关"
                if is_builtin and not deleted else None
            ),
            "builtin_fields_immutable": is_builtin,
        }

    @staticmethod
    def _param_rows(parameters: dict) -> list[dict]:
        """把 JSON Schema 解析成详情页「参数 / 类型 / 必填 / 说明」表格的行。"""
        if not isinstance(parameters, dict):
            return []
        props = parameters.get("properties") or {}
        required = set(parameters.get("required") or [])
        rows = []
        for name, spec in props.items():
            spec = spec if isinstance(spec, dict) else {}
            rows.append({
                "name": name,
                "type": spec.get("type", "any"),
                "required": name in required,
                "description": spec.get("description", ""),
            })
        return rows

    def _attach_tags(self, items: list[dict]) -> None:
        if not items:
            return
        ids = [i["id"] for i in items]
        placeholders = ",".join("?" * len(ids))
        rows = self.client.query(
            f"SELECT tool_id, tag_name FROM tool_tag WHERE tool_id IN ({placeholders}) "
            f"ORDER BY id", tuple(ids),
        )
        by_tool: dict[int, list[str]] = {}
        for r in rows:
            by_tool.setdefault(r["tool_id"], []).append(r["tag_name"])
        for i in items:
            i["tags"] = by_tool.get(i["id"], [])

    @staticmethod
    def _replace_tags(conn, tool_id: int, tags: list[str]) -> None:
        conn.execute("DELETE FROM tool_tag WHERE tool_id = ?", (tool_id,))
        seen = []
        for t in tags or []:
            t = (t or "").strip()
            if t and t not in seen:
                seen.append(t)
                conn.execute("INSERT OR IGNORE INTO tool_tag (tool_id, tag_name) VALUES (?, ?)",
                             (tool_id, t))

    @staticmethod
    def _audit(conn, tool_id, tool_name, action, diff, operator) -> None:
        conn.execute(
            "INSERT INTO tool_audit_log (tool_id, tool_name, action, field_diff, operator, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (tool_id, tool_name, action,
             json.dumps(diff, ensure_ascii=False) if diff else None,
             operator, _now()),
        )


# ─── 异常（路由层据此转成 HTTP 状态码）─────────────────
class AlreadyDeleted(RuntimeError):
    def __init__(self, tool_id):
        super().__init__(f"工具 {tool_id} 已被删除")


class NotDeleted(RuntimeError):
    def __init__(self, tool_id):
        super().__init__(f"工具 {tool_id} 未被删除")


class RestoreWindowExpired(RuntimeError):
    def __init__(self, tool_id, deleted_at):
        super().__init__(f"工具 {tool_id} 的恢复窗口已过期（删除于 {deleted_at}）")
        self.deleted_at = deleted_at


# ─── 时间辅助 ────────────────────────────────────────
def _plus_days(iso: str, days: int) -> str:
    from datetime import timedelta
    return (datetime.fromisoformat(iso) + timedelta(days=days)).isoformat(timespec="seconds")


def _days_ago(days: int) -> str:
    from datetime import timedelta
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")


def _days_since(iso: str) -> float:
    try:
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt).total_seconds() / 86400
    except Exception:
        return 0.0


# ─── 单例 ────────────────────────────────────────────
_repo: ToolRepository | None = None
_lock = threading.Lock()


def get_tool_repo() -> ToolRepository:
    global _repo
    if _repo is None:
        with _lock:
            if _repo is None:
                _repo = ToolRepository()
    return _repo
