"""对话管理接口的出入参。

设计依据：doc/对话落库-实施方案.md §4.1

⚠️ 校验策略：**长度类一律截断，语义类一律报错**。
   - 标题写长了（200 字）是「用户没数清楚」→ 截断到 100，不打断操作（B40）
   - 标题改成空串是「用户想表达一个非法状态」→ 400 拒绝（B39）
   反过来的话，前者会让用户困惑地丢掉一段文字，后者会存出一条没有标题的会话。
"""
from typing import Literal

from pydantic import BaseModel, field_validator

MAX_TITLE_LEN = 100
MAX_SYSTEM_PROMPT_LEN = 4000
MAX_MODEL_LEN = 64

ConvStatus = Literal["active", "completed", "archived"]


def _clean(s: str | None) -> str:
    """去掉首尾空白并把内部换行压成空格 —— 标题是单行展示的。"""
    return " ".join((s or "").split())


class ConvCreate(BaseModel):
    """POST /api/conversations

    ⚠️ 三个字段都可选：用户可以点「新对话」什么都不填直接开始。
       标题留空是**正常**的，会在首条消息落库时自动补上（B32）。
    """
    model: str = "default"
    title: str = ""
    system_prompt: str | None = None

    @field_validator("title")
    @classmethod
    def _v_title(cls, v: str) -> str:
        return _clean(v)[:MAX_TITLE_LEN]           # 截断，不报错

    @field_validator("model")
    @classmethod
    def _v_model(cls, v: str) -> str:
        # ⚠️ 不校验白名单：前端 MODEL_OPTIONS 是演示用的固定列表，
        #    将来可能由接口下发；现在拒绝未知 model 只会让联调莫名 400（B33）
        return (_clean(v) or "default")[:MAX_MODEL_LEN]

    @field_validator("system_prompt")
    @classmethod
    def _v_sp(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return v.strip()[:MAX_SYSTEM_PROMPT_LEN] or None


class ConvUpdate(BaseModel):
    """PUT /api/conversations/{id} —— 目前只支持改标题。

    ⚠️ `title` 给了就必须非空（B39）；不给表示不改。
       tags 见方案 §7 R1：本轮不实现，前端传了会被忽略。
    """
    title: str | None = None

    @field_validator("title")
    @classmethod
    def _v_title(cls, v: str | None) -> str | None:
        if v is None:
            return None
        cleaned = _clean(v)
        if not cleaned:
            raise ValueError("标题不能为空")
        return cleaned[:MAX_TITLE_LEN]


class ConvFlags(BaseModel):
    """PATCH /api/conversations/{id}/flags —— 置顶 / 归档。

    ⚠️ 两个字段都可选，只改传了的那个。都不传 = 无操作（返回当前状态，不报错）。
    """
    pinned: bool | None = None
    archived: bool | None = None
