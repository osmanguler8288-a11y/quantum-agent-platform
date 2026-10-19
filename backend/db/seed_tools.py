"""内置工具的 DB seed 与「代码↔DB 漂移」检测。

设计依据：doc/backdesign/工具库后端设计.md §3.3 / §6

核心原则 —— **契约字段 vs 运营字段**：
    契约字段（llm_description / parameters）永远以**代码**为准，漂移时自动纠正；
    运营字段（display_name / user_description / category / tags / icon / status）
    永远以 **DB** 为准，seed 绝不覆盖用户的编辑。
"""
import hashlib
import json
from datetime import datetime, timezone

from app.utils.logger import logger
from db.sqlite_client import get_client, DBUnavailable
from tools.register_all import iter_builtin_tool_defs


# ─────────────────────────────────────────────────────────────
# 分类（⚠️ 设计稿只画了 4 类，覆盖不了 5 个 memory_* 工具，故补「记忆」）
# ─────────────────────────────────────────────────────────────
SEED_CATEGORIES = [
    {"name": "量化计算", "sort_order": 10},
    {"name": "数据处理", "sort_order": 20},
    {"name": "结果分析", "sort_order": 30},
    {"name": "记忆",     "sort_order": 40},
    {"name": "外部服务", "sort_order": 50},
]

# ─────────────────────────────────────────────────────────────
# 内置工具的运营字段初始值。
# ⚠️ 只在**首次 INSERT** 时写入。用户改过之后，重新 seed 不会覆盖。
# ─────────────────────────────────────────────────────────────
TOOL_SEED_META = {
    "bash":               {"display_name": "Shell 命令执行",   "icon": "🖥", "category": "数据处理", "is_destructive": 1},
    "read_file":          {"display_name": "文件读取",         "icon": "📄", "category": "数据处理", "is_destructive": 0},
    "write_file":         {"display_name": "文件写入",         "icon": "💾", "category": "数据处理", "is_destructive": 1},
    "list_dir":           {"display_name": "目录浏览",         "icon": "📁", "category": "数据处理", "is_destructive": 0},
    "delete_file":        {"display_name": "文件删除",         "icon": "🗑", "category": "数据处理", "is_destructive": 1},
    "python_repl":        {"display_name": "Python 执行器",    "icon": "🐍", "category": "数据处理", "is_destructive": 0},
    "grep_file":          {"display_name": "文本检索",         "icon": "🔍", "category": "数据处理", "is_destructive": 0},
    "gaussian":           {"display_name": "Gaussian16 计算",  "icon": "⚗", "category": "量化计算", "is_destructive": 0},
    "eqv2_predict":       {"display_name": "EqV2 单点计算",    "icon": "⚡", "category": "量化计算", "is_destructive": 0},
    "eqv2_relax":         {"display_name": "EqV2 结构优化",    "icon": "🔻", "category": "量化计算", "is_destructive": 0},
    "multiwfn":           {"display_name": "Multiwfn 波函数分析", "icon": "📊", "category": "量化计算", "is_destructive": 0},
    "homo_lumo":          {"display_name": "前线轨道分析",     "icon": "🎯", "category": "结果分析", "is_destructive": 0},
    "dipole":             {"display_name": "偶极矩提取",       "icon": "🧭", "category": "结果分析", "is_destructive": 0},
    "memory_add":         {"display_name": "记忆写入",         "icon": "🧠", "category": "记忆",     "is_destructive": 0},
    "memory_search":      {"display_name": "记忆检索",         "icon": "🔎", "category": "记忆",     "is_destructive": 0},
    "memory_consolidate": {"display_name": "记忆整合",         "icon": "🔗", "category": "记忆",     "is_destructive": 0},
    "memory_forget":      {"display_name": "记忆遗忘",         "icon": "🧹", "category": "记忆",     "is_destructive": 0},
    "memory_history":     {"display_name": "记忆历史",         "icon": "📜", "category": "记忆",     "is_destructive": 0},
}

_HASH_PREFIX = "v1:"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _code_hash(description: str, parameters: dict) -> str:
    """契约字段的指纹。

    ⚠️ 必须 sort_keys 稳定序列化：dict 顺序变化会造成**假漂移**，
       导致每次启动都对全部工具做一次无效 UPDATE。
    带版本前缀：hash 算法本身变更时可整体失效，避免误判全量漂移。
    """
    raw = json.dumps(
        {"description": description, "parameters": parameters},
        sort_keys=True, ensure_ascii=False, separators=(",", ":"),
    )
    return _HASH_PREFIX + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _normalize_db_params(raw) -> str:
    """把 DB 里的 parameters JSON 归一化，以便与代码侧直接比较值。

    坏 JSON 不能让整个 seed 崩掉（照 memory/store.py 的带兜底反序列化思路）。
    """
    try:
        return json.dumps(json.loads(raw or "{}"), ensure_ascii=False, sort_keys=True)
    except Exception:
        return "<unparsable>"


def seed_all() -> dict:
    """幂等地把内置工具写入 DB。可重复执行，结果一致。

    返回统计：{categories, inserted, updated, skipped, disabled}
    """
    stats = {"categories": 0, "inserted": 0, "updated": 0, "skipped": 0, "disabled": 0}
    client = get_client()
    if not client.available:
        logger.warning("[seed] SQLite 不可用，跳过 seed（工具库降级为不可用）")
        return stats

    defs = iter_builtin_tool_defs()
    now = _now()

    try:
        with client.transaction() as conn:
            # ── 1. 分类：name 上有真 UNIQUE 约束，可安全用单语句 upsert ──
            for c in SEED_CATEGORIES:
                cur = conn.execute(
                    "INSERT INTO tool_category(name, sort_order, is_builtin, created_at) "
                    "VALUES (?, ?, 1, ?) ON CONFLICT(name) DO NOTHING",
                    (c["name"], c["sort_order"], now),
                )
                stats["categories"] += cur.rowcount
            cat_ids = {r["name"]: r["id"] for r in conn.execute("SELECT id, name FROM tool_category")}

            # ── 2. 读快照（一次读全，避免 17 次单条查询）──
            snap = {
                r["name"]: r
                for r in conn.execute(
                    "SELECT name, llm_description, parameters FROM tool WHERE deleted_at IS NULL"
                )
            }

            # ── 3. 逐个内置工具比对 ──
            for d in defs:
                name = d["name"]
                h = _code_hash(d["description"], d["parameters"])
                params_json = json.dumps(d["parameters"], ensure_ascii=False, sort_keys=True)

                if name not in snap:
                    meta = TOOL_SEED_META.get(name, {})
                    conn.execute(
                        "INSERT INTO tool (name, display_name, category_id, source, status, "
                        " icon, user_description, llm_description, parameters, param_template, "
                        " is_destructive, sort_order, created_at, updated_at) "
                        "VALUES (?, ?, ?, 'builtin', 'enabled', ?, ?, ?, ?, '{}', ?, 100, ?, ?)",
                        (
                            name,
                            meta.get("display_name", name),
                            cat_ids.get(meta.get("category", "数据处理")),
                            meta.get("icon", "🔧"),
                            # 初始「工具介绍」用代码描述的首句（人类可读），
                            # 用户可随时在工具库里改成更详细的 Markdown
                            d["description"].split("。")[0] + "。",
                            d["description"],
                            params_json,
                            meta.get("is_destructive", 0),
                            now, now,
                        ),
                    )
                    stats["inserted"] += 1
                    logger.info("[seed] 新增内置工具 {}（{}）", name, meta.get("display_name", name))

                elif (snap[name]["llm_description"] == d["description"]
                      and _normalize_db_params(snap[name]["parameters"]) == params_json):
                    stats["skipped"] += 1          # ← 零写入

                else:
                    # ⚠️ 只更新契约字段。运营字段（display_name/user_description/
                    #    category/tags/icon/status）属于用户，绝不覆盖。
                    conn.execute(
                        "UPDATE tool SET llm_description = ?, parameters = ?, updated_at = ? "
                        "WHERE name = ? AND deleted_at IS NULL",
                        (d["description"], params_json, now, name),
                    )
                    stats["updated"] += 1
                    logger.warning(
                        "[seed] [DRIFT] {} 契约字段已按代码纠正（运营字段未动）", name
                    )

                conn.execute(
                    "INSERT INTO tool_seed_state(tool_name, code_hash, seeded_at) VALUES (?, ?, ?) "
                    "ON CONFLICT(tool_name) DO UPDATE SET code_hash = excluded.code_hash, "
                    "seeded_at = excluded.seeded_at",
                    (name, h, now),
                )

            # ── 4. 代码里已消失的内置工具 → 停用（不物理删，保留调用历史）──
            alive = [d["name"] for d in defs]
            placeholders = ",".join("?" * len(alive))
            cur = conn.execute(
                f"UPDATE tool SET status = 'disabled', updated_at = ? "
                f"WHERE source = 'builtin' AND deleted_at IS NULL "
                f"  AND name NOT IN ({placeholders})",
                (now, *alive),
            )
            stats["disabled"] = cur.rowcount
            if cur.rowcount:
                logger.warning(
                    "[seed] 有 {} 个内置工具已从代码中移除，已标记为停用（未删除，保留调用历史）",
                    cur.rowcount,
                )

    except DBUnavailable as e:
        logger.error("[seed] 数据库不可用，seed 中止: {}", e)
    except Exception:
        logger.opt(exception=True).error("[seed] 执行失败，工具库可能不完整")

    logger.info(
        "[seed] 完成 | 分类新增={} 工具新增={} 契约更新={} 跳过={} 停用={}",
        stats["categories"], stats["inserted"], stats["updated"],
        stats["skipped"], stats["disabled"],
    )
    return stats
