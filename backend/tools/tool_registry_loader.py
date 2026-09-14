"""从 DB 构建 ToolRegistry，并支持热重建。

设计依据：doc/backdesign/工具库后端设计.md §6

核心原则（红线 ❌1 的落地）：
    **DB 只决定「哪些工具可见 + 展示元数据」，Python 函数引用永远只从代码取。**
    DB 里绝不出现可执行逻辑 —— 否则就是任意代码执行漏洞。

⚠️ 已知中间态（P5 之前）：
    planner 的工具清单仍硬编码在 agent/prompts/planner_prompt.txt 里（12 个），
    **不读 registry**。所以启停一个工具的效果是：
        ✅ 该工具**调不通**（registry 里查不到 → TOOL_NOT_FOUND）
        ❌ 但 planner 仍可能规划它
    要让启停完全生效，需等 P5 把 prompt 里的清单改成动态注入。
"""
import json
import threading

from app.utils.logger import logger
from db.tool_repo import get_tool_repo
from tools.register_all import builtin_tool_specs
from tools.tool_register import Tool, ToolRegistry

_lock = threading.RLock()
_registry: ToolRegistry | None = None
_mcp_client = None


def bind(mcp_client) -> None:
    """把 executor 正在使用的 MCPClient 实例交给 loader。

    ⚠️ 不能反过来 `import app.routes.workflow` —— workflow.py 在 import 期就构造 mcp，
       形成环依赖会直接炸。所以在 workflow.py 模块级调用一次 bind()。
    """
    global _mcp_client
    _mcp_client = mcp_client


def _func_index() -> dict:
    """name → 真实可调用对象。**唯一来源是代码**，DB 永不参与。"""
    return {spec["name"]: spec["func"] for spec in builtin_tool_specs()}


def _remote_stub(endpoint: str):
    """source='mcp' 的工具在 P6 之前的占位实现。

    抛出 NotImplementedError → 被 MCPClient._call_local 捕获 → 返回 error dict，
    实现「可管理但不可调用」的语义。
    """
    def _call(**_params):
        raise NotImplementedError(f"远程 MCP 调用尚未实现 (endpoint={endpoint})")
    return _call


def _load_json(raw, fallback):
    """带兜底的反序列化 —— 坏数据不能让整个 registry 构建失败。"""
    if not raw:
        return fallback
    try:
        return json.loads(raw)
    except Exception:
        return fallback


def build_registry_from_db(repo=None) -> ToolRegistry:
    """按 DB 中「启用且未删除」的工具构建 registry。"""
    repo = repo or get_tool_repo()
    registry = ToolRegistry()
    funcs = _func_index()
    skipped = 0

    for row in repo.list_enabled_for_agent():
        name = row["name"]
        if row["source"] == "builtin":
            func = funcs.get(name)
            if func is None:
                # DB 里有、代码里没有 —— 说明 seed 用了旧数据或代码被改过。
                # 记 error 并跳过，不静默忽略。
                logger.error("[registry] DB 有内置工具 {} 但代码里无对应实现，跳过", name)
                skipped += 1
                continue
        else:
            func = _remote_stub(row["endpoint"] or "")

        registry.register(Tool(
            name=name,
            description=row["llm_description"] or "",
            parameters=_load_json(row["parameters"], {}),
            func=func,
        ))

    if skipped:
        logger.warning("[registry] 有 {} 个工具因代码中无实现被跳过", skipped)
    return registry


def get_registry() -> ToolRegistry | None:
    return _registry


def reload_registry() -> tuple[bool, str | None]:
    """重建并热替换 registry。返回 (是否成功, 失败原因)。

    调用点（缺一不可）：
        - 应用启动（seed 之后）
        - PATCH /api/tools/{id}/status 成功后   ← 否则启停开关是假的
        - POST /api/tools 新建 MCP 工具后
        - DELETE / POST restore 后

    ⚠️ 单 worker 限制：`uvicorn --workers N` 时每个 worker 有独立 registry，
       改一个不会同步其他。当前部署是单 worker。
    """
    global _registry
    try:
        with _lock:
            new_registry = build_registry_from_db()
            _registry = new_registry
            _swap_into_client(new_registry)
        logger.info("[registry] 已重建，可见工具 {} 个", len(new_registry.list_tools()))
        return True, None
    except Exception as e:
        logger.opt(exception=True).error("[registry] 重建失败，沿用旧 registry")
        return False, str(e)


def _swap_into_client(new_registry: ToolRegistry) -> None:
    """把新 registry 换给 executor 正在使用的那个 MCPClient。

    ⚠️ 两个容易漏的点：
       1. `MCPClient.registry` 只是**持有引用** —— 新建一个 registry 对象不会影响
          已构造的 mcp，必须显式替换它持有的那个引用。
       2. 若 mcp 是可观测代理（InstrumentedMCPClient），其 __getattr__ 只做透传，
          直接 setattr 会在**代理上**生成遮蔽属性，真身反而收不到 —— 要写 _inner。
    """
    if _mcp_client is None:
        logger.debug("[registry] 未绑定 MCPClient，跳过替换（仅构建）")
        return
    target = getattr(_mcp_client, "_inner", _mcp_client)
    target.registry = new_registry
