"""会话仓储层 —— conversation / conversation_message 的唯一读写者。

设计依据：doc/对话落库-实施方案.md §2、§3

四条硬约束（都对应方案里的边界条件编号）：

1. **归属过滤在仓内闭环**（C1）。所有方法都要求 user_id 参数，SQL 一律
   `WHERE id = ? AND user_id = ?`。上层拿不到「不带 user_id 的查询方法」，
   越权在物理上不可能发生，而不是靠调用方自觉。

2. **消息只追加，永不 UPDATE / DELETE**（C2）。`append_messages()` 是唯一写口。
   这也是它不能用 `client.execute()` 逐条写、必须走 `transaction()` 的原因 ——
   seq 分配是「先读后写」，deferred 事务会锁升级。

3. **查不到一律返回 None / 空**，由路由层统一转 404。本层不区分
   「不存在 / 已删除 / 不属于你」—— 区分了就等于告诉攻击者「这个 id 存在」（B3）。

4. **写失败会抛 DBUnavailable**（B41）。对话链路里调用 append_messages 必须自己
   try/except（落库失败绝不能打断用户对话），管理接口则让它冒泡成 503（B42）。
"""
import re
import threading
import uuid
from datetime import datetime, timezone

from app.utils.logger import logger
from db.sqlite_client import get_client

# ─── 常量 ────────────────────────────────────────────
MAX_TITLE_LEN = 100        # 手工标题上限（超出截断，不报错 —— 见 B40）
MAX_KEYWORD_LEN = 100      # 搜索词上限（B27）
SNIPPET_LEN = 200          # 列表行摘要长度（B17）
AUTO_TITLE_LEN = 40        # 首条提问自动成为标题时的截断长度（B32）

_VALID_TABS = ("all", "active", "archived")

# 客户端 id 的白名单格式：字母数字 + 下划线/连字符，4~32 位。
# 后端生成的 12 位 hex、老前端的 8 位 hex 都在范围内。
_CLIENT_ID_PATTERN = re.compile(r"^[0-9A-Za-z_-]{4,32}$")

# 生成器并发写同一会话时的重试次数（B18）。单机 SQLite + BEGIN IMMEDIATE
# 下几乎不会触发，属于防御性代码。
_SEQ_RETRY = 2


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _new_id() -> str:
    """12 位十六进制（48 bit）。

    ⚠️ 不能用旧的 `uuid4()[:8]`（32 bit）—— 生日问题下约 7.7 万个会话就有
       50% 概率碰撞，而这里是**全局主键**，撞了就是两个用户争抢同一行。
    """
    return uuid.uuid4().hex[:12]


def sanitize_client_id(raw: str | None) -> str | None:
    """客户端传来的 id：只有格式合法才采信，否则丢弃（返回 None，调用方另起新 id）。

    ⚠️ 为什么必须校验：id 会**直接成为数据库主键**。不校验的话，
       任何一个 HTTP 客户端都能往主键里塞任意长度、任意内容的字符串
       （100KB 的 id、带换行的 id、控制字符……），既污染数据也浪费存储。
       老前端 localStorage 里的 8 位随机串（`^[0-9a-f]{8}$`）能通过，保持续接语义。

    ⚠️ 采信一个「格式合法但不存在」的 id 是**有意为之**（方案 §3.1 B4 情形 2）：
       会话归属由 user_id 决定，id 只是个名字。真正的越权尝试会走到情形 3
       —— 查得到但属于别人 → 换新 id 重建。
    """
    if not raw:
        return None
    raw = raw.strip()
    return raw if _CLIENT_ID_PATTERN.match(raw) else None


def _esc_like(s: str) -> str:
    """转义 LIKE 通配符（与 tool_repo._esc_like 同款）。

    ⚠️ 不转义时 keyword="%" 会匹配全部记录，"_" 匹配任意单字符 —— 搜索结果静默出错。
    """
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _derive_title(text: str) -> str:
    """首条提问 → 标题：去掉换行与多余空白，截断到 40 字符。"""
    t = " ".join((text or "").split())
    return t[:AUTO_TITLE_LEN]


def _snippet(text: str) -> str:
    return " ".join((text or "").split())[:SNIPPET_LEN]


def _row_to_summary(r) -> dict:
    """conversation 行 → 前端 ConvSummary。

    ⚠️ `archived` 是 `status == 'archived'` 的**派生布尔**，不是独立列。
       前端类型里两个字段都有，必须都返回 —— 少一个前端就是 undefined。
    ⚠️ `tags` 固定返回 []（方案 §7 R1：本轮不建 conversation_tag 表）。
       绝不能返回 null，否则前端 `tags.map()` 直接炸。
    """
    return {
        "id": r["id"],
        "title": r["title"],
        "status": r["status"],
        "model": r["model"],
        "tags": [],
        "snippet": r["snippet"],
        "message_count": r["message_count"],
        "pinned": bool(r["pinned"]),
        "archived": r["status"] == "archived",
        "created_at": r["created_at"],
        "updated_at": r["updated_at"],
    }


def _row_to_message(r) -> dict:
    return {
        "role": r["role"],
        "content": r["content"],
        "created_at": r["created_at"],
        "status": r["status"],
        "seq": r["seq"],
    }


class ConversationRepository:
    """会话与消息的 CRUD。所有方法都必须显式传 user_id。"""

    def __init__(self, client=None):
        self.client = client or get_client()

    # ══════════════════════════════════════════════════
    # 写：创建
    # ══════════════════════════════════════════════════
    def create(self, user_id: str, *, model: str = "default",
               title: str = "", system_prompt: str | None = None) -> dict:
        """新建会话，id 由后端生成。

        ⚠️ 主键碰撞时重试换 id（B4.5）—— 而不是让用户看到 500。
        """
        title = (title or "").strip()[:MAX_TITLE_LEN]
        now = _now()
        for _ in range(3):
            cid = _new_id()
            try:
                with self.client.transaction() as conn:
                    conn.execute(
                        "INSERT INTO conversation"
                        " (id, user_id, title, model, system_prompt, status, pinned,"
                        "  snippet, message_count, tool_calls, created_at, updated_at)"
                        " VALUES (?, ?, ?, ?, ?, 'active', 0, '', 0, 0, ?, ?)",
                        (cid, str(user_id), title, model or "default", system_prompt, now, now),
                    )
                logger.info("[conv-repo] 新建会话 id={} user={} title={!r}", cid, user_id, title)
                return self.get(cid, user_id)
            except Exception as e:
                # 只有主键冲突才值得重试；其余异常（含 DBUnavailable）直接上抛
                if "UNIQUE" not in str(e).upper() and "PRIMARY KEY" not in str(e).upper():
                    raise
                logger.warning("[conv-repo] 主键碰撞，重新生成 id: {}", e)
        raise RuntimeError("无法生成唯一会话 id")

    def get_or_create(self, conversation_id: str | None, user_id: str) -> dict:
        """按 id 取会话；不存在则创建（workflow 落库路径用）。

        三种情况（方案 B4）：
            1. id 存在且属于该用户     → 直接用
            2. id 不存在               → 用这个 id 建一条（仅当格式合法，见 sanitize_client_id）
            3. id 存在但**属于别人**   → 不报错，**换新 id 重建**

        第 3 种是最容易被忽略的：前端 localStorage 里一个残留的 id，
        在换账号登录后正好撞上别人的会话，直接 500 会让用户第一句话就发不出去。

        ⚠️ 入口先过 sanitize_client_id —— id 是要进主键的，不能原样采信。
        """
        conversation_id = sanitize_client_id(conversation_id)

        if conversation_id:
            existing = self.get(conversation_id, user_id)
            if existing is not None:
                return existing

            now = _now()
            try:
                with self.client.transaction() as conn:
                    # OR IGNORE：id 被别人占了就静默跳过，下面 SELECT 会落空
                    conn.execute(
                        "INSERT OR IGNORE INTO conversation"
                        " (id, user_id, title, model, status, pinned,"
                        "  snippet, message_count, tool_calls, created_at, updated_at)"
                        " VALUES (?, ?, '', 'default', 'active', 0, '', 0, 0, ?, ?)",
                        (conversation_id, str(user_id), now, now),
                    )
            except Exception:
                # 建不出来（DB 不可用）就走新建分支，至少让对话能继续
                logger.opt(exception=True).warning(
                    "[conv-repo] get_or_create 建行失败，改为新建 id={}", conversation_id
                )
                return self.create(user_id)

            got = self.get(conversation_id, user_id)
            if got is not None:
                logger.info("[conv-repo] 沿用已有 id={} user={}", conversation_id, user_id)
                return got

            logger.warning(
                "[conv-repo] id={} 已被其他用户占用，改用新 id（user={}）",
                conversation_id, user_id,
            )

        return self.create(user_id)

    # ══════════════════════════════════════════════════
    # 写：追加消息（热路径）
    # ══════════════════════════════════════════════════
    def append_messages(self, conversation_id: str, messages: list[dict],
                        *, tool_calls: int = 0) -> int:
        """追加若干条消息，返回实际写入条数。

        messages: [{"role": "user"|"assistant", "content": str,
                    "status": "ok"|"error"|"interrupted", "token_count": int}, ...]

        ⚠️ 空 content 的消息会被**跳过**（B15）—— 存进去会让详情页出现空气泡。
        ⚠️ 整个「读 MAX(seq) → 插 → 更新冗余列」必须在 BEGIN IMMEDIATE 事务里，
           否则并发时会分到同一个 seq 并撞唯一索引。
        ⚠️ 调用方（workflow）必须自己 try/except —— 落库失败不能打断用户对话（B14）。
        """
        rows = [m for m in messages if (m.get("content") or "").strip()]
        if not rows:
            return 0

        for attempt in range(_SEQ_RETRY + 1):
            try:
                return self._append_once(conversation_id, rows, tool_calls)
            except Exception as e:
                # 唯一索引冲突 → 重试一次；其余异常（含 DBUnavailable）上抛
                if attempt >= _SEQ_RETRY or "UNIQUE" not in str(e).upper():
                    raise
                logger.warning("[conv-repo] seq 冲突，重试 {}/{}: {}",
                               attempt + 1, _SEQ_RETRY, e)
        return 0

    def _append_once(self, conversation_id: str, rows: list[dict], tool_calls: int) -> int:
        now = _now()
        with self.client.transaction() as conn:
            # 会话必须存在且未删除 —— 否则外键会失败（foreign_keys=ON）
            cur = conn.execute(
                "SELECT id, title, snippet FROM conversation"
                " WHERE id = ? AND deleted_at IS NULL",
                (conversation_id,),
            )
            head = cur.fetchone()
            if head is None:
                raise LookupError(f"会话不存在或已删除: {conversation_id}")

            base = conn.execute(
                "SELECT COALESCE(MAX(seq), 0) AS m FROM conversation_message"
                " WHERE conversation_id = ?",
                (conversation_id,),
            ).fetchone()["m"]

            for i, m in enumerate(rows, start=1):
                conn.execute(
                    "INSERT INTO conversation_message"
                    " (conversation_id, seq, role, content, status, token_count, created_at)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        conversation_id, base + i,
                        m.get("role", "assistant"),
                        m.get("content") or "",
                        m.get("status", "ok"),
                        int(m.get("token_count") or 0),
                        now,
                    ),
                )

            # 冗余列在同事务内更新，保证列表页永不需要 JOIN 消息表（B22）
            first_user = next((m for m in rows if m.get("role") == "user"), None)
            new_title = head["title"]
            new_snippet = head["snippet"]
            if first_user:
                if not new_title:
                    new_title = _derive_title(first_user["content"])   # B32
                if not new_snippet:
                    new_snippet = _snippet(first_user["content"])

            conn.execute(
                "UPDATE conversation"
                " SET message_count = message_count + ?, tool_calls = tool_calls + ?,"
                "     title = ?, snippet = ?, updated_at = ?"
                " WHERE id = ?",
                (len(rows), tool_calls, new_title, new_snippet, now, conversation_id),
            )

        logger.info("[conv-repo] 追加消息 conv={} 条数={} seq={}..{}",
                    conversation_id, len(rows), base + 1, base + len(rows))
        return len(rows)

    # ══════════════════════════════════════════════════
    # 写：元数据
    # ══════════════════════════════════════════════════
    def update(self, conversation_id: str, user_id: str, *,
               title: str | None = None) -> dict | None:
        """改标题。查不到/已删除返回 None（路由层转 404）。

        ⚠️ 空标题在这里是「不修改」；要拒绝空标题由路由层的校验负责（B39）。
        """
        sets, params = [], []
        if title is not None:
            sets.append("title = ?")
            params.append(title.strip()[:MAX_TITLE_LEN])
        if not sets:
            return self.get(conversation_id, user_id)

        sets.append("updated_at = ?")
        params.extend([_now(), conversation_id, str(user_id)])
        n = self.client.execute(
            f"UPDATE conversation SET {', '.join(sets)}"
            " WHERE id = ? AND user_id = ? AND deleted_at IS NULL",
            tuple(params),
        )
        return self.get(conversation_id, user_id) if n else None

    def set_flags(self, conversation_id: str, user_id: str, *,
                  pinned: bool | None = None, archived: bool | None = None) -> dict | None:
        """置顶 / 归档。

        ⚠️ 归档走 status 列（不是独立 bool 列），因此与删除（deleted_at）天然正交（B36）。
        """
        sets, params = [], []
        if pinned is not None:
            sets.append("pinned = ?")
            params.append(1 if pinned else 0)
        if archived is not None:
            sets.append("status = ?")
            params.append("archived" if archived else "active")
        if not sets:
            return self.get(conversation_id, user_id)

        sets.append("updated_at = ?")
        params.extend([_now(), conversation_id, str(user_id)])
        n = self.client.execute(
            f"UPDATE conversation SET {', '.join(sets)}"
            " WHERE id = ? AND user_id = ? AND deleted_at IS NULL",
            tuple(params),
        )
        return self.get(conversation_id, user_id) if n else None

    def soft_delete(self, conversation_id: str, user_id: str) -> bool:
        """软删除。返回是否真的删掉了一条。

        ⚠️ `deleted_at IS NULL` 让重复删除变成幂等的 404，而不是 500（B37）。
        ⚠️ 消息表**不级联删除** —— 保留数据是将来做「恢复」的前提（B35）。
        """
        n = self.client.execute(
            "UPDATE conversation SET deleted_at = ?, status = 'archived', updated_at = ?"
            " WHERE id = ? AND user_id = ? AND deleted_at IS NULL",
            (_now(), _now(), conversation_id, str(user_id)),
        )
        return bool(n)

    # ══════════════════════════════════════════════════
    # 读
    # ══════════════════════════════════════════════════
    def get(self, conversation_id: str, user_id: str) -> dict | None:
        """单条会话（列表字段）。查不到/已删/不属于该用户 → None。"""
        r = self.client.query_one(
            "SELECT * FROM conversation"
            " WHERE id = ? AND user_id = ? AND deleted_at IS NULL",
            (conversation_id, str(user_id)),
        )
        return _row_to_summary(r) if r is not None else None

    def get_detail(self, conversation_id: str, user_id: str) -> dict | None:
        """详情 = 列表字段 + 首尾消息 + 统计。

        ⚠️ tokens / cost 当前恒为 0（方案 §7 R2：LLM 侧没有采集，不编造数据）。
           tool_calls 是真实值。
        """
        base = self.get(conversation_id, user_id)
        if base is None:
            return None

        first = self.client.query_one(
            "SELECT * FROM conversation_message WHERE conversation_id = ?"
            " ORDER BY seq ASC LIMIT 1",
            (conversation_id,),
        )
        last_reply = self.client.query_one(
            "SELECT * FROM conversation_message WHERE conversation_id = ?"
            " AND role = 'assistant' ORDER BY seq DESC LIMIT 1",
            (conversation_id,),
        )
        r = self.client.query_one(
            "SELECT * FROM conversation WHERE id = ? AND user_id = ?", (conversation_id, str(user_id))
        )
        return {
            **base,
            "system_prompt": r["system_prompt"] if r is not None else None,
            "tool_calls": r["tool_calls"] if r is not None else 0,
            "total_tokens": 0,
            "total_cost": 0.0,
            "first_message": _row_to_message(first) if first is not None else None,
            "last_reply": _row_to_message(last_reply) if last_reply is not None else None,
        }

    def list_conversations(self, user_id: str, *, keyword: str = "", tab: str = "all",
                           page: int = 1, page_size: int = 20) -> dict:
        """列表 + 分页 + 三个 Tab 的计数。

        ⚠️ tab 的定义（B28）：
             all      = 全部未删除
             active   = status != 'archived'（「进行中」= 尚未归档）
             archived = status == 'archived'
           这样 active + archived == all，计数相加自洽。

        ⚠️ counts 用一次 GROUP BY 拿全（B29），不是发三个 COUNT 查询。
        ⚠️ page 越界返回空 items，但 total 保持真实值（B24）。
        """
        where = ["user_id = ?", "deleted_at IS NULL"]
        params: list = [str(user_id)]

        if tab == "active":
            where.append("status != 'archived'")
        elif tab == "archived":
            where.append("status = 'archived'")

        keyword = " ".join((keyword or "").split())[:MAX_KEYWORD_LEN]   # B26/B27
        if keyword:
            like = f"%{_esc_like(keyword)}%"
            where.append("(title LIKE ? ESCAPE '\\' OR snippet LIKE ? ESCAPE '\\')")
            params.extend([like, like])

        where_sql = "WHERE " + " AND ".join(where)

        total = self.client.scalar(
            f"SELECT COUNT(*) FROM conversation {where_sql}", tuple(params), default=0
        )

        offset = (page - 1) * page_size
        rows = self.client.query(
            f"SELECT * FROM conversation {where_sql}"
            " ORDER BY pinned DESC, updated_at DESC LIMIT ? OFFSET ?",
            (*params, page_size, offset),
        )

        return {
            "items": [_row_to_summary(r) for r in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
            "counts": self.counts(str(user_id)),
        }

    def counts(self, user_id: str) -> dict:
        """三个 Tab 的计数（一次查询）。"""
        rows = self.client.query(
            "SELECT status, COUNT(*) AS n FROM conversation"
            " WHERE user_id = ? AND deleted_at IS NULL GROUP BY status",
            (str(user_id),),
        )
        by_status = {r["status"]: r["n"] for r in rows}
        archived = by_status.get("archived", 0)
        total = sum(by_status.values())
        return {"all": total, "active": total - archived, "archived": archived}

    def list_messages(self, conversation_id: str, user_id: str, *,
                      page: int = 1, page_size: int = 200) -> dict | None:
        """取会话消息。会话不存在/不属于该用户 → None。

        ⚠️ 分页语义是「**从最新往前翻**」，page=1 是最新的一页；
           返回时按 seq **升序**排列（聊天界面要从上往下读）。
           这样超长会话默认拿到的是最近的上下文，而不是远古的第一页。
        """
        if self.get(conversation_id, user_id) is None:
            return None

        total = self.client.scalar(
            "SELECT COUNT(*) FROM conversation_message WHERE conversation_id = ?",
            (conversation_id,), default=0,
        )
        offset = (page - 1) * page_size
        rows = self.client.query(
            "SELECT * FROM conversation_message WHERE conversation_id = ?"
            " ORDER BY seq DESC LIMIT ? OFFSET ?",
            (conversation_id, page_size, offset),
        )
        items = [_row_to_message(r) for r in reversed(rows)]
        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "has_more": offset + len(items) < total,
        }

    def get_full_history(self, conversation_id: str, user_id: str,
                         limit: int = 200) -> list[dict]:
        """给 workflow 拼上下文用：最近 limit 条，按 seq 升序。

        与 list_messages 的区别是它**不抛 404**，查不到就返回空列表 ——
        拼上下文失败不能打断对话。
        """
        if not conversation_id:
            return []
        try:
            rows = self.client.query(
                "SELECT * FROM conversation_message WHERE conversation_id = ?"
                " ORDER BY seq DESC LIMIT ?",
                (conversation_id, limit),
            )
        except Exception:
            logger.opt(exception=True).warning(
                "[conv-repo] 读历史失败，本轮按无历史处理 conv={}", conversation_id
            )
            return []
        return [
            {"role": r["role"], "content": r["content"], "created_at": r["created_at"]}
            for r in reversed(rows)
        ]

    def search_messages(self, user_id: str, *, keyword: str = "",
                        limit: int = 10) -> list[dict]:
        """跨会话搜索消息（MCP 工具 conversation_history 用）。

        ⚠️ JOIN 上 conversation 做归属过滤 —— 只靠 message 表是查不出「这条属于谁」的，
           这正是 Redis 方案（只有 session_id）做不到多用户隔离的原因。
        """
        keyword = " ".join((keyword or "").split())[:MAX_KEYWORD_LEN]
        if keyword:
            like = f"%{_esc_like(keyword)}%"
            rows = self.client.query(
                "SELECT m.*, c.title AS conv_title FROM conversation_message m"
                " JOIN conversation c ON c.id = m.conversation_id"
                " WHERE c.user_id = ? AND c.deleted_at IS NULL AND m.content LIKE ? ESCAPE '\\'"
                " ORDER BY m.created_at DESC LIMIT ?",
                (str(user_id), like, limit),
            )
        else:
            rows = self.client.query(
                "SELECT m.*, c.title AS conv_title FROM conversation_message m"
                " JOIN conversation c ON c.id = m.conversation_id"
                " WHERE c.user_id = ? AND c.deleted_at IS NULL"
                " ORDER BY m.created_at DESC LIMIT ?",
                (str(user_id), limit),
            )
        return [
            {
                "conversation_id": r["conversation_id"],
                "title": r["conv_title"],
                "role": r["role"],
                "content": r["content"],
                "created_at": r["created_at"],
            }
            for r in rows
        ]


# ─── 单例 ────────────────────────────────────────────
_repo: ConversationRepository | None = None
_lock = threading.Lock()


def get_conversation_repo() -> ConversationRepository:
    global _repo
    if _repo is None:
        with _lock:
            if _repo is None:
                _repo = ConversationRepository()
    return _repo
