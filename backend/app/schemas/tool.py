"""工具库的请求/响应模型与校验器。

设计依据：doc/backdesign/工具库后端设计.md §4、§5

⚠️ 本模块承担了设计文档里标注的大部分「输入校验」边界条件：
    - name 必须是合法标识符且**强制小写**（SQLite 的 UNIQUE 大小写敏感，
      不归一化会共存 Bash / bash 两个"同名"工具）
    - source 与 endpoint 必须配套（mcp 必须有地址，builtin 必须没有）
    - param_template 必须能用 parameters 校验通过 —— 含 bool/int 陷阱
"""
import json
import re
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
ENDPOINT_PATTERN = re.compile(r"^mcp://[a-z0-9]([a-z0-9.-]*)(/[A-Za-z0-9._/-]*)?$")

MAX_TAGS = 10
MAX_TAG_LEN = 20
MAX_DESC_LEN = 2000
MAX_DISPLAY_NAME_LEN = 50
MAX_KEYWORD_LEN = 100

# 内置工具**不可修改**的字段（红线 ❌3）。
# 请求里带了这些字段直接拒绝，而不是静默忽略 —— 静默忽略会让调用方以为改成功了。
IMMUTABLE_WHEN_BUILTIN = ("name", "source", "endpoint", "parameters", "llm_description")

# JSON Schema 支持的基础类型 → Python 类型判定函数
# ⚠️ bool 必须先判：Python 里 isinstance(True, int) 是 True，
#    不先判 bool 的话 {"cores": true} 会被 integer 放行。
_TYPE_CHECKS = {
    "string": lambda v: isinstance(v, str),
    "integer": lambda v: (not isinstance(v, bool)) and isinstance(v, int),
    "number": lambda v: (not isinstance(v, bool)) and isinstance(v, (int, float)),
    "boolean": lambda v: isinstance(v, bool),
    "array": lambda v: isinstance(v, list),
    "object": lambda v: isinstance(v, dict),
}


class ToolCreate(BaseModel):
    name: str
    display_name: str
    category_id: int
    source: str
    user_description: str
    endpoint: Optional[str] = None
    icon: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    parameters: dict = Field(default_factory=dict)
    param_template: dict = Field(default_factory=dict)
    llm_description: Optional[str] = None
    status: str = "enabled"
    is_destructive: bool = False

    @field_validator("name")
    @classmethod
    def _check_name(cls, v: str) -> str:
        v = (v or "").strip().lower()      # ⚠️ 强制小写
        if not NAME_PATTERN.match(v):
            raise ValueError("工具标识只能是小写字母开头、由小写字母/数字/下划线组成，长度 1~64")
        return v

    @field_validator("display_name")
    @classmethod
    def _check_display_name(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("工具名称不能为空")
        if len(v) > MAX_DISPLAY_NAME_LEN:
            raise ValueError(f"工具名称最长 {MAX_DISPLAY_NAME_LEN} 字符")
        return v

    @field_validator("user_description")
    @classmethod
    def _check_desc(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("工具介绍不能为空")
        if len(v) > MAX_DESC_LEN:
            raise ValueError(f"工具介绍最长 {MAX_DESC_LEN} 字符")
        return v

    @field_validator("source")
    @classmethod
    def _check_source(cls, v: str) -> str:
        if v not in ("builtin", "mcp"):
            raise ValueError("来源类型只能是 builtin 或 mcp")
        return v

    @field_validator("status")
    @classmethod
    def _check_status(cls, v: str) -> str:
        if v not in ("enabled", "disabled"):
            raise ValueError("状态只能是 enabled 或 disabled")
        return v

    @field_validator("tags")
    @classmethod
    def _check_tags(cls, v: list[str]) -> list[str]:
        cleaned, seen = [], []
        for t in v or []:
            t = (t or "").strip()
            if not t:
                continue                     # 空标签静默丢弃，不报错
            if len(t) > MAX_TAG_LEN:
                raise ValueError(f"标签「{t}」超过 {MAX_TAG_LEN} 字符")
            if t not in seen:
                seen.append(t)
                cleaned.append(t)
        if len(cleaned) > MAX_TAGS:
            raise ValueError(f"标签最多 {MAX_TAGS} 个")
        return cleaned

    @model_validator(mode="after")
    def _check_consistency(self):
        _validate_endpoint(self.source, self.endpoint)
        _validate_parameters(self.parameters)
        _validate_param_template(self.parameters, self.param_template)
        return self


class ToolUpdate(BaseModel):
    display_name: Optional[str] = None
    category_id: Optional[int] = None
    user_description: Optional[str] = None
    llm_description: Optional[str] = None
    endpoint: Optional[str] = None
    icon: Optional[str] = None
    tags: Optional[list[str]] = None
    parameters: Optional[dict] = None
    param_template: Optional[dict] = None
    status: Optional[str] = None
    is_destructive: Optional[bool] = None
    sort_order: Optional[int] = None

    @field_validator("display_name")
    @classmethod
    def _check_display_name(cls, v):
        if v is None:
            return v
        v = v.strip()
        if not v or len(v) > MAX_DISPLAY_NAME_LEN:
            raise ValueError(f"工具名称需为 1~{MAX_DISPLAY_NAME_LEN} 字符")
        return v

    @field_validator("user_description")
    @classmethod
    def _check_desc(cls, v):
        if v is None:
            return v
        v = v.strip()
        if not v or len(v) > MAX_DESC_LEN:
            raise ValueError(f"工具介绍需为 1~{MAX_DESC_LEN} 字符")
        return v

    @field_validator("status")
    @classmethod
    def _check_status(cls, v):
        if v is not None and v not in ("enabled", "disabled"):
            raise ValueError("状态只能是 enabled 或 disabled")
        return v

    @field_validator("tags")
    @classmethod
    def _check_tags(cls, v):
        if v is None:
            return v
        return ToolCreate._check_tags(v)     # 复用同一套去重/长度规则


class ToolStatusPatch(BaseModel):
    status: str

    @field_validator("status")
    @classmethod
    def _check_status(cls, v: str) -> str:
        if v not in ("enabled", "disabled"):
            raise ValueError("状态只能是 enabled 或 disabled")
        return v


# ─────────────────────────────────────────────────────────────
# 校验器
# ─────────────────────────────────────────────────────────────
def _validate_endpoint(source: str, endpoint: Optional[str]) -> None:
    if source == "mcp":
        if not endpoint:
            raise ValueError("来源为 MCP 接入时，必须填写 MCP 服务地址")
        if not ENDPOINT_PATTERN.match(endpoint):
            raise ValueError("MCP 服务地址格式非法，应形如 mcp://calc-cluster/gaussian16")
    else:  # builtin
        if endpoint:
            raise ValueError("内置工具不应填写 MCP 服务地址")


def _validate_parameters(parameters: Any) -> None:
    if not isinstance(parameters, dict):
        raise ValueError("parameters 必须是 JSON 对象")
    props = parameters.get("properties") or {}
    if not isinstance(props, dict):
        raise ValueError("parameters.properties 必须是 JSON 对象")
    for key, spec in props.items():
        if not isinstance(spec, dict):
            raise ValueError(f"参数「{key}」的定义必须是对象")
        ptype = spec.get("type")
        if not ptype:
            raise ValueError(f"参数「{key}」缺少 type 字段（参数说明表无法渲染）")
        if ptype not in _TYPE_CHECKS:
            raise ValueError(f"参数「{key}」的类型 {ptype} 不支持，仅支持 {list(_TYPE_CHECKS)}")
        if ptype in ("object", "array"):
            raise ValueError(f"参数「{key}」为嵌套类型，当前版本暂不支持（参数说明表仅支持扁平结构）")
    required = parameters.get("required") or []
    if not isinstance(required, list):
        raise ValueError("parameters.required 必须是数组")
    unknown = [r for r in required if r not in props]
    if unknown:
        raise ValueError(f"required 中的 {unknown} 未在 properties 中定义")


def _validate_param_template(parameters: dict, template: Any) -> None:
    """参数模板必须能被 parameters(JSON Schema) 约束住。

    约束：template 的每个 key 必须存在于 properties，且 value 类型匹配。
    template 缺少 required 字段是**允许**的 —— 它是「预设」不是「完整实例」。
    """
    if not isinstance(template, dict):
        raise ValueError("参数模板必须是 JSON 对象")
    if not template:
        return

    props = (parameters or {}).get("properties") or {}
    if not props:
        raise ValueError("未定义任何参数，参数模板应为空")

    for key, value in template.items():
        if key not in props:
            raise ValueError(f"参数模板中的「{key}」未在参数定义（parameters）中声明")
        ptype = (props[key] or {}).get("type")
        check = _TYPE_CHECKS.get(ptype)
        if check and value is not None and not check(value):
            shown = "布尔值" if isinstance(value, bool) else type(value).__name__
            raise ValueError(
                f"参数模板「{key}」的类型不匹配：期望 {ptype}，实际是 {shown}"
            )


def parse_json_field(raw, fallback):
    """容错解析请求里的 JSON 字符串字段（前端可能传字符串）。"""
    if isinstance(raw, (dict, list)):
        return raw
    if not raw:
        return fallback
    try:
        return json.loads(raw)
    except Exception:
        return fallback
