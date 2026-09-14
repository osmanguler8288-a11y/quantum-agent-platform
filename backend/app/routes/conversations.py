"""对话管理 REST 接口。

设计依据：doc/对话落库-实施方案.md §4

⚠️ 与工具库接口（app/routes/tools.py）保持同一套约定：

1. **错误响应格式**：`error` 必须是**字符串**，错误码放**平级的 code** 字段。
   前端 frontend/src/api/client.ts 是 `data?.error || data?.detail`，
   若 error 改成对象，界面会直接显示 "[object Object]"。

2. **查不到一律 404，不用 403**。401/403 会告诉调用者「这个 id 是存在的，
   只是不归你」—— 等于给了一个枚举别人会话 id 的探针（B3）。

3. **本文件一行 SQL 都不写**。归属过滤全部收敛在 db/conversation_repo.py 里，
   路由层拿不到「不带 user_id 的查询方法」，越权在物理上不可能发生（C1）。
"""
import time

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.schemas.conversation import ConvCreate, ConvFlags, ConvUpdate
from app.utils.logger import logger
from db.conversation_repo import MAX_KEYWORD_LEN, get_conversation_repo
from db.sqlite_client import DBUnavailable

router = APIRouter()

MAX_PAGE_SIZE = 100
DEFAULT_PAGE_SIZE = 20
# 聊天页一次拉全部上下文，上限比列表大得多
MAX_MSG_PAGE_SIZE = 500
DEFAULT_MSG_PAGE_SIZE = 200

_VALID_TABS = ("all", "active", "archived")


# ─────────────────────────────────────────────────────────────
# 公共辅助（与 tools.py 同款，刻意各自保留一份以保持路由自洽）
# ─────────────────────────────────────────────────────────────
def _fail(status_code: int, code: str, message: str, detail=None) -> JSONResponse:
    """统一错误响应。⚠️ error 是字符串，code 平级。"""
    body = {"error": message, "code": code}
    if detail is not None:
        body["detail"] = detail
    return JSONResponse(status_code=status_code, content=body)


def _inject_user(request: Request) -> str:
    """用户标识来源：Go 网关注入的 X-User-ID。

    ⚠️ 网关注入的是**数字 ID**（JWT 里的 user_id），不是用户名。
       直连 :8001 时这个 header 无从网关注入，会落到 default_user ——
       所以 FastAPI 端口绝不能对外暴露（方案 §3.1 B1）。
    """
    return request.headers.get("X-User-ID") or "default_user"


def _db_down(e: Exception) -> JSONResponse:
    """DB 不可用 → 503。

    ⚠️ 会话列表**不能**在 DB 挂掉时返回空数组 —— 用户会以为自己的对话被删光了。
       宁可明确报错（B42）。
    """
    logger.warning("[conversations] 存储不可用: {}", e)
    return _fail(503, "DB_UNAVAILABLE", "会话存储暂时不可用，请稍后重试")


def _not_found() -> JSONResponse:
    return _fail(404, "CONVERSATION_NOT_FOUND", "会话不存在")


def _parse_pagination(page: int, page_size: int, max_size: int = MAX_PAGE_SIZE):
    """分页参数校验。返回 (page, page_size, error_response)。"""
    if page < 1:
        return None, None, _fail(400, "INVALID_PARAMETER", "page 必须大于等于 1")
    if page_size < 1 or page_size > max_size:
        return None, None, _fail(
            400, "INVALID_PARAMETER", f"page_size 必须在 1~{max_size} 之间"
        )
    return page, page_size, None


class _Trace:
    """一次会话操作的链路日志（与 tools.py 的 _OpTrace 同款）。

        [conversations] ▶ create | user=1 | model=gpt-4o
        [conv-repo]     [conv-repo] 新建会话 id=a0df8c794a50 user=1
        [conversations] ✔ create | id=a0df8c794a50 | 耗时=3ms

    写操作走 INFO（落盘），读操作走 DEBUG（只在终端可见，避免列表刷屏）。
    """

    def __init__(self, action: str, request: Request, *, debug: bool = False, **fields):
        self.action = action
        self.t0 = time.perf_counter()
        self.user = _inject_user(request)
        self._emit = logger.debug if debug else logger.info
        extra = " ".join(f"{k}={v}" for k, v in fields.items() if v not in (None, ""))
        self._emit("[conversations] ▶ {} | user={}{}",
                   action, self.user, f" | {extra}" if extra else "")

    def done(self, result: str = "") -> None:
        self._emit("[conversations] ✔ {} | 耗时={:.0f}ms{}",
                   self.action, (time.perf_counter() - self.t0) * 1000,
                   f" | {result}" if result else "")

    def failed(self, message: str, code: str = "") -> None:
        # 失败一律 warning —— 失败比成功更值得被看到
        logger.warning("[conversations] ✖ {} | 耗时={:.0f}ms | {} [{}]",
                       self.action, (time.perf_counter() - self.t0) * 1000,
                       message, code or "-")


# ═════════════════════════════════════════════════════════════
# 列表 / 新建
# ═════════════════════════════════════════════════════════════
@router.get("")
async def list_conversations(request: Request, keyword: str = "", tab: str = "all",
                             page: int = 1, page_size: int = DEFAULT_PAGE_SIZE):
    trace = _Trace("list", request, debug=True, keyword=keyword, tab=tab, page=page)
    page, page_size, err = _parse_pagination(page, page_size)
    if err:
        trace.failed("分页参数非法", "INVALID_PARAMETER")
        return err
    if tab not in _VALID_TABS:
        trace.failed(f"tab 非法: {tab}", "INVALID_PARAMETER")
        return _fail(400, "INVALID_PARAMETER",
                     f"tab 只能是 {' / '.join(_VALID_TABS)}")

    try:
        data = get_conversation_repo().list_conversations(
            _inject_user(request),
            keyword=(keyword or "")[:MAX_KEYWORD_LEN],
            tab=tab, page=page, page_size=page_size,
        )
    except DBUnavailable as e:
        trace.failed("存储不可用", "DB_UNAVAILABLE")
        return _db_down(e)

    trace.done(f"条数={len(data['items'])} total={data['total']} counts={data['counts']}")
    return JSONResponse(content=data)


@router.post("")
async def create_conversation(payload: ConvCreate, request: Request):
    trace = _Trace("create", request, model=payload.model, title=payload.title)
    try:
        # ⚠️ id 由后端生成，前端不自己造 —— 全局主键必须单一来源（C6）
        data = get_conversation_repo().create(
            _inject_user(request),
            model=payload.model, title=payload.title,
            system_prompt=payload.system_prompt,
        )
    except DBUnavailable as e:
        trace.failed("存储不可用", "DB_UNAVAILABLE")
        return _db_down(e)

    trace.done(f"id={data['id']}")
    return JSONResponse(status_code=201, content=data)


# ═════════════════════════════════════════════════════════════
# 单条会话
# ═════════════════════════════════════════════════════════════
@router.get("/{conversation_id}")
async def get_conversation(conversation_id: str, request: Request):
    trace = _Trace("detail", request, debug=True, id=conversation_id)
    try:
        data = get_conversation_repo().get_detail(conversation_id, _inject_user(request))
    except DBUnavailable as e:
        trace.failed("存储不可用", "DB_UNAVAILABLE")
        return _db_down(e)

    if data is None:
        trace.failed("不存在", "CONVERSATION_NOT_FOUND")
        return _not_found()
    trace.done(f"id={conversation_id} 消息数={data['message_count']}")
    return JSONResponse(content=data)


@router.get("/{conversation_id}/messages")
async def list_messages(conversation_id: str, request: Request,
                        page: int = 1, page_size: int = DEFAULT_MSG_PAGE_SIZE):
    """聊天页回填历史消息用。

    ⚠️ 分页语义是「**从最新往前翻**」：page=1 是最新的一页，返回时按时间升序。
       超长会话因此默认拿到最近上下文，而不是远古的第一页。
    """
    trace = _Trace("messages", request, debug=True, id=conversation_id)
    page, page_size, err = _parse_pagination(page, page_size, MAX_MSG_PAGE_SIZE)
    if err:
        trace.failed("分页参数非法", "INVALID_PARAMETER")
        return err

    try:
        data = get_conversation_repo().list_messages(
            conversation_id, _inject_user(request), page=page, page_size=page_size,
        )
    except DBUnavailable as e:
        trace.failed("存储不可用", "DB_UNAVAILABLE")
        return _db_down(e)

    if data is None:
        trace.failed("不存在", "CONVERSATION_NOT_FOUND")
        return _not_found()
    trace.done(f"条数={len(data['items'])} total={data['total']}")
    return JSONResponse(content=data)


@router.put("/{conversation_id}")
async def update_conversation(conversation_id: str, payload: ConvUpdate, request: Request):
    trace = _Trace("update", request, id=conversation_id)
    try:
        data = get_conversation_repo().update(
            conversation_id, _inject_user(request), title=payload.title,
        )
    except DBUnavailable as e:
        trace.failed("存储不可用", "DB_UNAVAILABLE")
        return _db_down(e)

    if data is None:
        trace.failed("不存在", "CONVERSATION_NOT_FOUND")
        return _not_found()
    trace.done(f"id={conversation_id} title={data['title']!r}")
    return JSONResponse(content=data)


@router.patch("/{conversation_id}/flags")
async def set_flags(conversation_id: str, payload: ConvFlags, request: Request):
    """置顶 / 归档。

    ⚠️ 归档是 `status='archived'`，与软删除（deleted_at）**正交**：
       归档的会话仍出现在「已归档」Tab 里，删除的则哪儿都不出现（B36）。
    """
    trace = _Trace("flags", request, id=conversation_id,
                   pinned=payload.pinned, archived=payload.archived)
    try:
        data = get_conversation_repo().set_flags(
            conversation_id, _inject_user(request),
            pinned=payload.pinned, archived=payload.archived,
        )
    except DBUnavailable as e:
        trace.failed("存储不可用", "DB_UNAVAILABLE")
        return _db_down(e)

    if data is None:
        trace.failed("不存在", "CONVERSATION_NOT_FOUND")
        return _not_found()
    trace.done(f"id={conversation_id} pinned={data['pinned']} archived={data['archived']}")
    return JSONResponse(content=data)


@router.delete("/{conversation_id}")
async def delete_conversation(conversation_id: str, request: Request):
    """软删除。

    ⚠️ 重复删除返回 404 而不是 500 —— `deleted_at IS NULL` 让这个操作幂等（B37）。
    ⚠️ 消息表**不级联删除**，数据保留是将来做「恢复」的前提（B35）。
    """
    trace = _Trace("delete", request, id=conversation_id)
    try:
        ok = get_conversation_repo().soft_delete(conversation_id, _inject_user(request))
    except DBUnavailable as e:
        trace.failed("存储不可用", "DB_UNAVAILABLE")
        return _db_down(e)

    if not ok:
        trace.failed("不存在或已删除", "CONVERSATION_NOT_FOUND")
        return _not_found()
    trace.done(f"id={conversation_id}")
    return JSONResponse(content={"id": conversation_id})
