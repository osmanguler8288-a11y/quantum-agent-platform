"""工具库数据库 schema（纯 DDL，零业务依赖）。

设计依据：doc/backdesign/工具库后端设计.md §3

⚠️ 三个容易踩的 SQLite 特性（都已在本文件处理）：
    1. `name` 的唯一性用**部分唯一索引**（WHERE deleted_at IS NULL），不是列级 UNIQUE。
       软删除的行仍然在表里，列级 UNIQUE 会占住 name，导致「删掉再同名重建」直接 500。
    2. 外键在 SQLite 里**默认关闭**，必须每建一个连接就 `PRAGMA foreign_keys=ON`，
       否则 ON DELETE SET NULL / CASCADE 全是摆设。见 sqlite_client.py。
    3. 时间统一存 TEXT（ISO-8601 UTC 字符串）—— SQLite 无原生时间类型，
       TEXT 可直接字符串排序且人类可读。
"""

SCHEMA_VERSION = 2

DDL = """
-- ============================================================
-- 工具分类
-- ============================================================
CREATE TABLE IF NOT EXISTS tool_category (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL UNIQUE,
    sort_order  INTEGER NOT NULL DEFAULT 0,
    is_builtin  INTEGER NOT NULL DEFAULT 0,   -- 1 = 内置分类，不可删
    created_at  TEXT    NOT NULL
);

-- ============================================================
-- 工具主表
-- ============================================================
CREATE TABLE IF NOT EXISTS tool (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,

    -- 机器标识（小写存储，应用层保证）
    name              TEXT    NOT NULL,
    display_name      TEXT    NOT NULL,

    category_id       INTEGER NOT NULL REFERENCES tool_category(id),
    source            TEXT    NOT NULL CHECK (source IN ('builtin', 'mcp')),

    -- status 与 deleted_at 正交：停用 ≠ 删除
    status            TEXT    NOT NULL DEFAULT 'enabled'
                              CHECK (status IN ('enabled', 'disabled')),
    deleted_at        TEXT,

    -- MCP 接入地址，如 'mcp://calc-cluster/gaussian16'
    endpoint          TEXT,

    -- 展示字段
    icon              TEXT    NOT NULL DEFAULT '🔧',
    user_description  TEXT    NOT NULL DEFAULT '',   -- 给人看的 Markdown
    llm_description   TEXT    NOT NULL DEFAULT '',   -- 给 LLM 看的（原 Tool.description）

    -- 契约字段（JSON 文本）
    parameters        TEXT    NOT NULL DEFAULT '{}', -- JSON Schema，执行契约
    param_template    TEXT    NOT NULL DEFAULT '{}', -- 参数默认值，展示/预设用

    is_destructive    INTEGER NOT NULL DEFAULT 0,
    sort_order        INTEGER NOT NULL DEFAULT 0,

    created_at        TEXT    NOT NULL,
    updated_at        TEXT    NOT NULL
);

-- ⚠️ 部分唯一索引：只约束「未删除的工具之间 name 唯一」，软删的行不占名字
CREATE UNIQUE INDEX IF NOT EXISTS idx_tool_name_active
    ON tool(name) WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_tool_status   ON tool(status, deleted_at);
CREATE INDEX IF NOT EXISTS idx_tool_category ON tool(category_id, deleted_at);
CREATE INDEX IF NOT EXISTS idx_tool_source   ON tool(source);

-- ============================================================
-- 工具标签（规范化，便于搜索与计数）
-- ============================================================
CREATE TABLE IF NOT EXISTS tool_tag (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    tool_id   INTEGER NOT NULL REFERENCES tool(id) ON DELETE CASCADE,
    tag_name  TEXT    NOT NULL,
    UNIQUE (tool_id, tag_name)
);

CREATE INDEX IF NOT EXISTS idx_tag_name ON tool_tag(tag_name);

-- ============================================================
-- 调用埋点（统计四宫格与最近调用记录的唯一来源）
-- ============================================================
CREATE TABLE IF NOT EXISTS tool_invocation (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,

    -- ⚠️ 用 SET NULL 而非 CASCADE：删除工具时「历史调用记录仍会保留」是产品承诺。
    -- tool_name 冗余存一份，硬删后历史依然可读。
    tool_id       INTEGER REFERENCES tool(id) ON DELETE SET NULL,
    tool_name     TEXT    NOT NULL,

    session_id    TEXT,
    user_id       TEXT    NOT NULL DEFAULT 'default_user',
    task_title    TEXT,
    step_index    INTEGER,

    status        TEXT    NOT NULL CHECK (status IN ('success', 'error')),
    error_code    TEXT,
    error_message TEXT,
    duration_ms   INTEGER,

    -- 只存参数指纹，不存全量参数（参数可能含文件路径等敏感信息）
    params_digest TEXT,
    started_at    TEXT    NOT NULL,
    finished_at   TEXT
);

CREATE INDEX IF NOT EXISTS idx_inv_tool_started ON tool_invocation(tool_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_inv_name_started ON tool_invocation(tool_name, started_at DESC);

-- ============================================================
-- 变更审计
-- ============================================================
CREATE TABLE IF NOT EXISTS tool_audit_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    tool_id    INTEGER,
    tool_name  TEXT NOT NULL,
    action     TEXT NOT NULL,   -- create/update/enable/disable/delete/restore
    field_diff TEXT,            -- JSON: {"before": {...}, "after": {...}}
    operator   TEXT NOT NULL DEFAULT 'default_user',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_audit_tool ON tool_audit_log(tool_name, created_at DESC);

-- ============================================================
-- seed 漂移检测
-- ============================================================
CREATE TABLE IF NOT EXISTS tool_seed_state (
    tool_name TEXT PRIMARY KEY,
    code_hash TEXT NOT NULL,   -- 代码侧定义的 sha256，带 v1: 前缀
    seeded_at TEXT NOT NULL
);

-- ============================================================
-- schema 版本（供将来迁移用）
-- SQLite 的 ALTER TABLE 不支持改类型/删列，加字段容易、改结构必须走重建表。
-- ============================================================
CREATE TABLE IF NOT EXISTS schema_version (
    version    INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

-- ============================================================
-- 会话主表（v2 新增）
--
-- ⚠️ id 用 TEXT 且**值就是 workflow 的 session_id** —— 一个实体只允许一个标识符。
--    若另开一个自增 INTEGER id，同一段对话就有两个 id，语义必然漂移
--    （同 user_id 那个坑：网关发数字、前端发用户名）。
-- ============================================================
CREATE TABLE IF NOT EXISTS conversation (
    id            TEXT    PRIMARY KEY,

    -- 归属。来源是 X-User-ID（网关注入的数字 ID），不是用户名
    user_id       TEXT    NOT NULL,

    title         TEXT    NOT NULL DEFAULT '',   -- 空标题由首条提问兜底，见 repo.touch_on_append
    model         TEXT    NOT NULL DEFAULT 'default',
    system_prompt TEXT,

    -- status / pinned / deleted_at 三者正交（沿用 tool 表已验证的模型）：
    --   归档可逆、删除不可见于任何列表、置顶只是排序权重
    status        TEXT    NOT NULL DEFAULT 'active'
                          CHECK (status IN ('active', 'completed', 'archived')),
    pinned        INTEGER NOT NULL DEFAULT 0,
    deleted_at    TEXT,

    -- 列表页冗余列：避免每一行都去子查询 message 表（N+1）
    snippet       TEXT    NOT NULL DEFAULT '',
    message_count INTEGER NOT NULL DEFAULT 0,
    tool_calls    INTEGER NOT NULL DEFAULT 0,

    created_at    TEXT    NOT NULL,
    updated_at    TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_conv_user_updated
    ON conversation(user_id, updated_at DESC) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_conv_user_status
    ON conversation(user_id, status, deleted_at);

-- ============================================================
-- 消息表（v2 新增）—— 只追加，永不 UPDATE / DELETE
--
-- ⚠️ 外键**不带 ON DELETE CASCADE**：会话是软删（deleted_at），消息要保留，
--    这是将来做「恢复」的前提。查询侧靠 conversation.deleted_at IS NULL 过滤。
-- ============================================================
CREATE TABLE IF NOT EXISTS conversation_message (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT    NOT NULL REFERENCES conversation(id),

    seq             INTEGER NOT NULL,            -- 会话内递增序号，从 1 开始
    role            TEXT    NOT NULL CHECK (role IN ('user', 'assistant')),
    content         TEXT    NOT NULL DEFAULT '',

    status          TEXT    NOT NULL DEFAULT 'ok'
                            CHECK (status IN ('ok', 'error', 'interrupted')),
    token_count     INTEGER NOT NULL DEFAULT 0,

    created_at      TEXT    NOT NULL
);

-- ⚠️ 唯一约束是并发安全的**兜底**：并发写同一会话时它会失败并触发重试，
--    而不是像 Redis 那套「读全量→改→写全量」一样静默覆盖丢消息。
CREATE UNIQUE INDEX IF NOT EXISTS idx_msg_conv_seq
    ON conversation_message(conversation_id, seq);
"""


def apply_schema(conn) -> None:
    """幂等建表。多次调用安全。"""
    conn.executescript(DDL)


def current_version(conn) -> int:
    row = conn.execute("SELECT MAX(version) AS v FROM schema_version").fetchone()
    v = row["v"] if row is not None else None
    return int(v) if v is not None else 0
