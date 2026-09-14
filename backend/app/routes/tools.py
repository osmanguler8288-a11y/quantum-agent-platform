"""工具库 REST 接口。

设计依据：doc/backdesign/工具库后端设计.md §4

⚠️ 两个必须遵守的约定：

1. **路由定义顺序**：静态路径 `/categories` 必须定义在动态路径 `/{tool_id}` **之前**。
   FastAPI 按定义顺序匹配，若 `/{tool_id}` 在前，`/api/tools/categories` 会先命中它，
   因 tool_id 是 int 无法解析 "categories" 而返回 422，而不是走到分类接口。

2. **错误响应格式**：`error` 必须是**字符串**，错误码放**平级的 code** 字段。
   前端 frontend/src/api/client.ts 的实现是 `data?.error || data?.detail`，
   若 error 改成对象，界面会直接显示 "[object Object]"。
"""
import time

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.schemas.tool import (
    IMMUTABLE_WHEN_BUILTIN, MAX_KEYWORD_LEN, ToolCreate, ToolStatusPatch, ToolUpdate,
)
from app.utils.logger import logger, mask_sensitive
from db.sqlite_client import DBUnavailable, get_client
from db.tool_repo import (
    AlreadyDeleted, NotDeleted, RestoreWindowExpired, get_tool_repo,
)
from tools.tool_registry_loader import reload_registry

router = APIRouter()

MAX_PAGE_SIZE = 100
DEFAULT_PAGE_SIZE = 9   # 沿用设计稿主列表


# ─────────────────────────────────────────────────────────────
# 公共辅助
# ─────────────────────────────────────────────────────────────
def _fail(status_code: int, code: str, message: str, detail=None) -> JSONResponse:
    """统一错误响应。⚠️ error 是字符串，code 平级 —— 见模块 docstring。"""
    body = {"error": message, "code": code}
    if detail is not None:
        body["detail"] = detail
    return JSONResponse(status_code=status_code, content=body)


def _inject_user(request: Request) -> str:
    """用户标识来源。

    ⚠️ 已知限制：这是 Go 网关注入的 header，**当前没有任何校验**，可被伪造。
       工具库是平台级共享资源，本轮不做用户级隔离；operator 字段先写入审计日志，
       为将来真正的鉴权留位。
    """
    return request.headers.get("X-User-ID") or "default_user"


def _ctx(request: Request) -> str:
    """给日志用的请求标识。"""
    return request.headers.get("X-Request-ID") or "-"


# ─────────────────────────────────────────────────────────────
# 链路追踪
#
# 一次工具库操作会在日志里留下这样一条完整链路：
#
#   [tools] ▶ create | user=lihua | name=orca source=mcp tags=[CASSCF]   ← 请求开始 + 入参
#   [db.tool_repo] [tools] 新增工具 id=20 name=orca source=mcp            ← DB 写入
#   [tool_registry_loader] [registry] 已重建，可见工具 18 个              ← registry 重建
#   [tools] ✔ create | id=20 | 耗时=7ms                                   ← 结果
#   [request_context] [http] POST /api/tools | status=201 | 7ms           ← HTTP 层
#
# 写操作走 INFO（会落盘），读操作走 DEBUG（只在终端可见，避免列表/搜索刷屏）。
# ─────────────────────────────────────────────────────────────
class _OpTrace:
    def __init__(self, action: str, request: Request, params: dict | None = None,
                 *, debug: bool = False):
        self.action = action
        self.t0 = time.perf_counter()
        self.user = _inject_user(request)
        self._emit = logger.debug if debug else logger.info
        self._emit("[tools] ▶ {} | user={} | {}",
                   action, self.user, _fmt_params(params or {}) or "（无参数）")

    def done(self, result: str = "") -> None:
        self._emit("[tools] ✔ {} | 耗时={:.0f}ms{}",
                   self.action, self._elapsed(), f" | {result}" if result else "")

    def failed(self, message: str, code: str = "") -> None:
        # 失败一律 warning（读操作也一样）—— 失败比成功更值得被看到
        logger.warning("[tools] ✖ {} | 耗时={:.0f}ms | {} [{}]",
                       self.action, self._elapsed(), message, code or "-")

    def _elapsed(self) -> float:
        return (time.perf_counter() - self.t0) * 1000


def _fmt_params(params: dict) -> str:
    """把入参压成单行日志：先脱敏，再截断，避免长文本淹没日志。"""
    safe = mask_sensitive(params)
    parts = []
    for k, v in safe.items():
        if v is None or v == "":
            continue
        if isinstance(v, str):
            v = v.replace("\n", "\\n")
            if len(v) > 60:
                v = v[:60] + "…"
        elif isinstance(v, (list, tuple)):
            items = [str(x) for x in v[:6]]
            v = "[" + ",".join(items) + ("…+%d" % (len(v) - 6) if len(v) > 6 else "") + "]"
        elif isinstance(v, dict):
            keys = list(v.keys())[:6]
            v = "{" + ",".join(keys) + ("…" if len(v) > 6 else "") + "}"
        parts.append(f"{k}={v}")
    return " ".join(parts)


def _contract_fields(payload) -> dict:
    """提取「这次改了哪些字段」，用于 update 的入参日志。"""
    dumped = payload.model_dump(exclude_unset=True)
    return {"fields": sorted(dumped.keys()), "endpoint": dumped.get("endpoint")}


def _parse_pagination(page: int, page_size: int):
    """分页参数校验。返回 (page, page_size, error_response)。"""
    if page < 1:
        return None, None, _fail(400, "INVALID_PARAMETER", "page 必须大于等于 1")
    if page_size < 1 or page_size > MAX_PAGE_SIZE:
        return None, None, _fail(
            400, "INVALID_PARAMETER", f"page_size 必须在 1~{MAX_PAGE_SIZE} 之间"
        )
    return page, page_size, None


# ═════════════════════════════════════════════════════════════
# 分类 —— ⚠️ 必须在 /{tool_id} 之前定义
# ═════════════════════════════════════════════════════════════
@router.get("/categories")
async def list_categories(request: Request):
    trace = _OpTrace("list_categories", request, debug=True)
    try:
        data = get_tool_repo().list_categories()
        trace.done(f"分类数={len(data['items'])} 工具总数={data['total']}")
        return JSONResponse(content=data)
    except Exception as e:
        logger.opt(exception=True).error("[tools] 查询分类失败")
        trace.failed(str(e), "INTERNAL_ERROR")
        return _fail(500, "INTERNAL_ERROR", "查询分类失败")


# ═════════════════════════════════════════════════════════════
# 列表
# ═════════════════════════════════════════════════════════════
@router.get("")
async def list_tools(
    request: Request,
    keyword: str | None = None,
    category: str | None = None,
    status: str = "all",
    source: str | None = None,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
    include_deleted: bool = False,
):
    trace = _OpTrace("list", request, {
        "keyword": keyword, "category": category, "status": status,
        "source": source, "page": page, "page_size": page_size,
        "include_deleted": include_deleted or None,
    }, debug=True)

    page, page_size, err = _parse_pagination(page, page_size)
    if err:
        trace.failed("分页参数非法", "INVALID_PARAMETER")
        return err

    keyword = (keyword or "").strip() or None
    if keyword and len(keyword) > MAX_KEYWORD_LEN:
        trace.failed("关键词过长", "INVALID_PARAMETER")
        return _fail(400, "INVALID_PARAMETER", f"搜索关键词最长 {MAX_KEYWORD_LEN} 字符")
    if status not in ("all", "enabled", "disabled"):
        trace.failed(f"status 非法: {status}", "INVALID_PARAMETER")
        return _fail(400, "INVALID_PARAMETER", "status 只能是 all / enabled / disabled")

    try:
        result = get_tool_repo().list_tools(
            keyword=keyword,
            category=(category or "").strip() or None,   # 不存在的分类 → 空结果，不报 404
            status=None if status == "all" else status,
            source=source,
            page=page,
            page_size=page_size,
            include_deleted=include_deleted,
        )
        trace.done(f"命中={result['total']} 本页={len(result['items'])}")
        return JSONResponse(content={
            "items": result["items"],
            "total": result["total"],
            "page": page,
            "page_size": page_size,
            "enabled_count": result["enabled_count"],
            "request_id": _ctx(request),
        })
    except DBUnavailable:
        trace.failed("数据库不可用", "DB_UNAVAILABLE")
        return _fail(503, "DB_UNAVAILABLE", "工具库数据库暂不可用，请稍后重试")
    except Exception as e:
        logger.opt(exception=True).error("[tools] 查询工具列表失败")
        trace.failed(str(e), "INTERNAL_ERROR")
        return _fail(500, "INTERNAL_ERROR", "查询工具列表失败")


# ═════════════════════════════════════════════════════════════
# 新增
# ═════════════════════════════════════════════════════════════
@router.post("")
async def create_tool(payload: ToolCreate, request: Request):
    trace = _OpTrace("create", request, {
        "name": payload.name,
        "source": payload.source,
        "category_id": payload.category_id,
        "tags": payload.tags,
        "desc_len": len(payload.user_description),
        "param_keys": list((payload.parameters or {}).get("properties", {}).keys()),
    })
    operator = _inject_user(request)
    repo = get_tool_repo()

    # ⚠️ 内置工具只能由 seed 写入（代码是唯一真源，DB 不存可执行逻辑）。
    #    通过 API 创建 source='builtin' 会产生一条「代码里没有实现」的记录：
    #    它永远调不通，还会让每次 registry 重建都报错。
    if payload.source == "builtin":
        trace.failed("不允许通过接口创建内置工具", "BUILTIN_NOT_CREATABLE")
        return _fail(
            400, "BUILTIN_NOT_CREATABLE",
            "内置工具由平台代码定义，不能通过接口创建。如需接入外部服务请选择「MCP 接入」。",
        )

    if repo.resolve_id_by_name(payload.name) is not None:
        trace.failed(f"工具标识 '{payload.name}' 已存在", "TOOL_NAME_CONFLICT")
        return _fail(409, "TOOL_NAME_CONFLICT", f"工具标识 '{payload.name}' 已存在",
                     {"name": payload.name})
    if not _category_exists(payload.category_id):
        trace.failed("指定的分类不存在", "INVALID_PARAMETER")
        return _fail(400, "INVALID_PARAMETER", "指定的分类不存在")

    try:
        tool_id = repo.create_tool(payload.model_dump(), operator)
    except DBUnavailable:
        trace.failed("数据库不可用", "DB_UNAVAILABLE")
        return _fail(503, "DB_UNAVAILABLE", "工具库数据库暂不可用，请稍后重试")
    except Exception as e:
        logger.opt(exception=True).error("[tools] 新增工具失败 name={}", payload.name)
        trace.failed(str(e), "INTERNAL_ERROR")
        return _fail(500, "INTERNAL_ERROR", "新增工具失败")

    reloaded, warning = reload_registry()   # 可见集合变了，必须重建
    if warning:
        trace.failed(f"registry 重建失败: {warning}", "REGISTRY_RELOAD_FAILED")

    detail = repo.get_tool(tool_id, include_deleted=True, with_stats=True)
    detail["registry_reloaded"] = reloaded
    if warning:
        detail["warning"] = warning
    trace.done(f"id={tool_id} registry_reloaded={reloaded}")
    return JSONResponse(status_code=201, content=detail)


# ═════════════════════════════════════════════════════════════
# 详情
# ═════════════════════════════════════════════════════════════
@router.get("/{tool_id}")
async def get_tool(tool_id: int, request: Request,
                   with_stats: bool = True, invocation_limit: int = 5):
    trace = _OpTrace("detail", request,
                     {"id": tool_id, "with_stats": with_stats}, debug=True)
    try:
        tool = get_tool_repo().get_tool(
            tool_id,
            with_stats=with_stats,
            invocation_limit=max(0, min(invocation_limit, 50)),
        )
    except DBUnavailable:
        trace.failed("数据库不可用", "DB_UNAVAILABLE")
        return _fail(503, "DB_UNAVAILABLE", "工具库数据库暂不可用，请稍后重试")
    except Exception as e:
        logger.opt(exception=True).error("[tools] 查询工具详情失败 id={}", tool_id)
        trace.failed(str(e), "INTERNAL_ERROR")
        return _fail(500, "INTERNAL_ERROR", "查询工具详情失败")

    if tool is None:
        trace.failed(f"工具 {tool_id} 不存在", "TOOL_NOT_FOUND")
        return _fail(404, "TOOL_NOT_FOUND", f"工具 {tool_id} 不存在")
    trace.done(f"name={tool['name']} 调用次数={tool['invocation_count']}")
    return JSONResponse(content=tool)


# ═════════════════════════════════════════════════════════════
# 编辑
# ═════════════════════════════════════════════════════════════
@router.put("/{tool_id}")
async def update_tool(tool_id: int, payload: ToolUpdate, request: Request):
    trace = _OpTrace("update", request, {"id": tool_id, **_contract_fields(payload)})
    operator = _inject_user(request)
    repo = get_tool_repo()

    current = repo.get_tool(tool_id, include_deleted=True)
    if current is None:
        trace.failed(f"工具 {tool_id} 不存在", "TOOL_NOT_FOUND")
        return _fail(404, "TOOL_NOT_FOUND", f"工具 {tool_id} 不存在")
    if current["deleted"]:
        trace.failed("工具已被删除", "TOOL_ALREADY_DELETED")
        return _fail(409, "TOOL_ALREADY_DELETED", "该工具已被删除，请先恢复再编辑")

    # 内置工具的契约字段不可改（红线 ❌3）—— 显式拒绝而不是静默忽略
    if current["source"] == "builtin":
        touched = [f for f in IMMUTABLE_WHEN_BUILTIN
                   if getattr(payload, f, None) is not None]
        if touched:
            trace.failed(f"内置工具不可修改字段 {'、'.join(touched)}", "BUILTIN_FIELD_IMMUTABLE")
            return _fail(
                403, "BUILTIN_FIELD_IMMUTABLE",
                f"内置工具不可修改这些字段：{'、'.join(touched)}",
                {"fields": touched},
            )

    if payload.category_id is not None and not _category_exists(payload.category_id):
        trace.failed("指定的分类不存在", "INVALID_PARAMETER")
        return _fail(400, "INVALID_PARAMETER", "指定的分类不存在")

    # 只传了 parameters 或只传了 param_template 时，用**另一侧**重新校验一致性
    new_params = payload.parameters if payload.parameters is not None else current["parameters"]
    new_template = payload.param_template if payload.param_template is not None else current["param_template"]
    try:
        _revalidate_contract(new_params, new_template)
    except ValueError as e:
        trace.failed(f"参数契约不一致: {e}", "PARAM_TEMPLATE_MISMATCH")
        return _fail(400, "PARAM_TEMPLATE_MISMATCH", str(e))

    # endpoint 改动需与 source 配套
    if payload.endpoint is not None:
        if current["source"] == "mcp" and not payload.endpoint.strip():
            trace.failed("MCP 工具的服务地址不能为空", "INVALID_ENDPOINT")
            return _fail(400, "INVALID_ENDPOINT", "MCP 工具的服务地址不能为空")

    try:
        updated = repo.update_tool(tool_id, payload.model_dump(exclude_unset=True), operator)
    except DBUnavailable:
        trace.failed("数据库不可用", "DB_UNAVAILABLE")
        return _fail(503, "DB_UNAVAILABLE", "工具库数据库暂不可用，请稍后重试")
    except Exception as e:
        logger.opt(exception=True).error("[tools] 更新工具失败 id={}", tool_id)
        trace.failed(str(e), "INTERNAL_ERROR")
        return _fail(500, "INTERNAL_ERROR", "更新工具失败")

    reloaded, warning = reload_registry()
    if warning:
        trace.failed(f"registry 重建失败: {warning}", "REGISTRY_RELOAD_FAILED")

    updated["registry_reloaded"] = reloaded
    if warning:
        updated["warning"] = warning
    trace.done(f"id={tool_id} name={current['name']} registry_reloaded={reloaded}")
    return JSONResponse(content=updated)


# ═════════════════════════════════════════════════════════════
# 启停
# ═════════════════════════════════════════════════════════════
@router.patch("/{tool_id}/status")
async def patch_status(tool_id: int, payload: ToolStatusPatch, request: Request):
    trace = _OpTrace("set_status", request, {"id": tool_id, "status": payload.status})
    operator = _inject_user(request)
    repo = get_tool_repo()

    try:
        result = repo.set_status(tool_id, payload.status, operator)
    except DBUnavailable:
        trace.failed("数据库不可用", "DB_UNAVAILABLE")
        return _fail(503, "DB_UNAVAILABLE", "工具库数据库暂不可用，请稍后重试")
    except Exception as e:
        logger.opt(exception=True).error("[tools] 启停工具失败 id={}", tool_id)
        trace.failed(str(e), "INTERNAL_ERROR")
        return _fail(500, "INTERNAL_ERROR", "启停工具失败")

    if result is None:
        trace.failed(f"工具 {tool_id} 不存在", "TOOL_NOT_FOUND")
        return _fail(404, "TOOL_NOT_FOUND", f"工具 {tool_id} 不存在")

    # ⚠️ 重建 registry 是「启停开关真正生效」的唯一途径 —— 失败必须显式暴露，不能静默
    reloaded, warning = reload_registry()
    if warning:
        trace.failed(f"registry 重建失败: {warning}", "REGISTRY_RELOAD_FAILED")

    body = {"id": result["id"], "name": result["name"], "status": result["status"],
            "changed": result["changed"], "registry_reloaded": reloaded}
    if warning:
        body["warning"] = warning
    if not result["changed"]:
        # 幂等：设为当前值不算失败，但值得记一笔，便于排查「为什么点了没反应」
        trace.done(f"name={result['name']} 已是 {result['status']}，无变更")
    else:
        trace.done(f"name={result['name']} → {result['status']} registry_reloaded={reloaded}")
    return JSONResponse(content=body)


# ═════════════════════════════════════════════════════════════
# 删除（软删）
# ═════════════════════════════════════════════════════════════
@router.delete("/{tool_id}")
async def delete_tool(tool_id: int, request: Request):
    trace = _OpTrace("delete", request, {"id": tool_id})
    operator = _inject_user(request)
    repo = get_tool_repo()

    current = repo.get_tool(tool_id, include_deleted=True)
    if current is None:
        trace.failed(f"工具 {tool_id} 不存在", "TOOL_NOT_FOUND")
        return _fail(404, "TOOL_NOT_FOUND", f"工具 {tool_id} 不存在")
    if current["deleted"]:
        trace.failed("工具已被删除", "TOOL_ALREADY_DELETED")
        return _fail(409, "TOOL_ALREADY_DELETED", "该工具已被删除")
    # 内置工具是 Agent 干活的基础，删了工作流直接瘫痪（决策 D3）
    if current["source"] == "builtin":
        trace.failed(f"内置工具 {current['name']} 不可删除", "BUILTIN_NOT_DELETABLE")
        return _fail(409, "BUILTIN_NOT_DELETABLE",
                     "内置工具不可删除，如需停用请使用启停开关")

    try:
        result = repo.soft_delete(tool_id, operator)
    except AlreadyDeleted:
        trace.failed("工具已被删除", "TOOL_ALREADY_DELETED")
        return _fail(409, "TOOL_ALREADY_DELETED", "该工具已被删除")
    except DBUnavailable:
        trace.failed("数据库不可用", "DB_UNAVAILABLE")
        return _fail(503, "DB_UNAVAILABLE", "工具库数据库暂不可用，请稍后重试")
    except Exception as e:
        logger.opt(exception=True).error("[tools] 删除工具失败 id={}", tool_id)
        trace.failed(str(e), "INTERNAL_ERROR")
        return _fail(500, "INTERNAL_ERROR", "删除工具失败")

    reloaded, _ = reload_registry()
    result["registry_reloaded"] = reloaded
    # 删除前近 30 天调用量 —— 供前端确认弹窗展示风险
    result["recent_30d_invocations"] = repo.get_stats(
        tool_id, tool_name=current["name"]
    )["recent_30d_invocations"]
    trace.done(
        f"name={current['name']} 近30天调用={result['recent_30d_invocations']} "
        f"可恢复至={result['restorable_until'][:10]}"
    )
    return JSONResponse(content=result)


# ═════════════════════════════════════════════════════════════
# 恢复
# ═════════════════════════════════════════════════════════════
@router.post("/{tool_id}/restore")
async def restore_tool(tool_id: int, request: Request):
    trace = _OpTrace("restore", request, {"id": tool_id})
    operator = _inject_user(request)
    repo = get_tool_repo()

    try:
        result = repo.restore(tool_id, operator)
    except NotDeleted:
        trace.failed("工具未被删除，无需恢复", "TOOL_NOT_DELETED")
        return _fail(409, "TOOL_NOT_DELETED", "该工具未被删除，无需恢复")
    except RestoreWindowExpired as e:
        trace.failed(f"已超过 7 天恢复窗口（删除于 {e.deleted_at}）", "RESTORE_WINDOW_EXPIRED")
        return _fail(410, "RESTORE_WINDOW_EXPIRED",
                     "已超过 7 天恢复窗口，无法恢复", {"deleted_at": e.deleted_at})
    except DBUnavailable:
        trace.failed("数据库不可用", "DB_UNAVAILABLE")
        return _fail(503, "DB_UNAVAILABLE", "工具库数据库暂不可用，请稍后重试")
    except Exception as e:
        logger.opt(exception=True).error("[tools] 恢复工具失败 id={}", tool_id)
        trace.failed(str(e), "INTERNAL_ERROR")
        return _fail(500, "INTERNAL_ERROR", "恢复工具失败")

    if result is None:
        trace.failed(f"工具 {tool_id} 不存在", "TOOL_NOT_FOUND")
        return _fail(404, "TOOL_NOT_FOUND", f"工具 {tool_id} 不存在")

    reloaded, _ = reload_registry()
    result["registry_reloaded"] = reloaded
    trace.done(f"name={result['name']} 恢复后 status={result['status']} registry_reloaded={reloaded}")
    return JSONResponse(content=result)


# ═════════════════════════════════════════════════════════════
# 调用记录
# ═════════════════════════════════════════════════════════════
@router.get("/{tool_id}/invocations")
async def list_invocations(tool_id: int, request: Request, page: int = 1,
                           page_size: int = 20, status: str = "all"):
    trace = _OpTrace("list_invocations", request,
                     {"id": tool_id, "status": status, "page": page}, debug=True)

    page, page_size, err = _parse_pagination(page, page_size)
    if err:
        trace.failed("分页参数非法", "INVALID_PARAMETER")
        return err
    if status not in ("all", "success", "error"):
        trace.failed(f"status 非法: {status}", "INVALID_PARAMETER")
        return _fail(400, "INVALID_PARAMETER", "status 只能是 all / success / error")

    repo = get_tool_repo()
    if repo.get_tool(tool_id, include_deleted=True) is None:
        trace.failed(f"工具 {tool_id} 不存在", "TOOL_NOT_FOUND")
        return _fail(404, "TOOL_NOT_FOUND", f"工具 {tool_id} 不存在")

    try:
        result = repo.list_invocations(
            tool_id, page=page, page_size=page_size,
            status=None if status == "all" else status,
        )
    except DBUnavailable:
        trace.failed("数据库不可用", "DB_UNAVAILABLE")
        return _fail(503, "DB_UNAVAILABLE", "工具库数据库暂不可用，请稍后重试")
    except Exception as e:
        logger.opt(exception=True).error("[tools] 查询调用记录失败 id={}", tool_id)
        trace.failed(str(e), "INTERNAL_ERROR")
        return _fail(500, "INTERNAL_ERROR", "查询调用记录失败")

    trace.done(f"total={result['total']}")
    return JSONResponse(content={
        "items": result["items"], "total": result["total"],
        "page": page, "page_size": page_size,
    })


# ─────────────────────────────────────────────────────────────
def _category_exists(category_id: int) -> bool:
    return get_client().scalar(
        "SELECT 1 FROM tool_category WHERE id = ?", (category_id,)
    ) is not None


def _revalidate_contract(parameters, param_template) -> None:
    """更新时重新校验参数契约（只更新一侧时用另一侧的既有值补齐）。"""
    from app.schemas.tool import _validate_parameters, _validate_param_template
    _validate_parameters(parameters)
    _validate_param_template(parameters, param_template)
