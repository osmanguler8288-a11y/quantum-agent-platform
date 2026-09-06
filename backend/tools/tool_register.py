"""
Tool Registry — MCP 兼容的工具注册中心

Tool 数据类的字段对齐 MCP 协议的 tool 定义：
  - name:        工具名（唯一标识）
  - description: 工具描述（给 LLM 看的，越详细越好）
  - parameters:  JSON Schema 格式的输入参数定义

未来迁移到真正的 MCP 协议时：
  - Tool.name / Tool.description / Tool.parameters → tools/list 响应
  - Tool.func(**params)                          → tools/call 处理器
  ———— Tool 定义一行不用改，只改传输层。
"""

from dataclasses import dataclass, field
from typing import Callable, Any


@dataclass
class Tool:
    """MCP 兼容的工具定义"""
    name: str
    description: str
    parameters: dict          # JSON Schema for input
    func: Callable[..., str]  # 实际执行函数，返回字符串结果


class ToolRegistry:
    """工具注册中心 — 管理所有可用工具"""

    def __init__(self):
        self._tools: dict[str, Tool] = {}

    # ─── 注册 ───────────────────────────────────────
    def register(self, tool: Tool):
        """注册一个 Tool 对象"""
        if tool.name in self._tools:
            print(f"[registry] [WARN] override: {tool.name}")
        self._tools[tool.name] = tool
        print(f"[registry] [OK] {tool.name}")


    def register_function(self, name: str, description: str,
                          parameters: dict, func: Callable[..., str]):
        """快捷注册：传函数 + 元信息，内部包装为 Tool"""
        tool = Tool(name=name, description=description,
                    parameters=parameters, func=func)
        self.register(tool)

    # ─── 查询 ───────────────────────────────────────
    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def list_tools(self) -> list[dict]:
        """返回所有工具的 MCP 格式摘要（给 Planner 看）"""
        return [
            {"name": t.name, "description": t.description}
            for t in self._tools.values()
        ]

    def list_tools_text(self) -> str:
        """返回可供 Planner prompt 直接注入的工具白名单"""
        lines = []
        for t in self._tools.values():
            lines.append(f"- {t.name}: {t.description}")
        return "\n".join(lines)

    # ─── 调用 ───────────────────────────────────────
    def call(self, name: str, params: dict) -> str:
        """
        查找工具并执行，返回字符串结果。
        如果工具不存在或执行失败，返回错误信息字符串（不抛异常）。
        """
        tool = self._tools.get(name)
        if tool is None:
            return f"[错误] 工具 '{name}' 未注册。可用工具: {list(self._tools.keys())}"

        try:
            return tool.func(**params)
        except TypeError as e:
            return f"[错误] 工具 '{name}' 参数不匹配: {e}\n期望参数: {tool.parameters}"
        except Exception as e:
            return f"[错误] 工具 '{name}' 执行失败: {e}"


        