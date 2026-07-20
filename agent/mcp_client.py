"""
MCP Client — 统一工具调用入口

当前阶段（方案 A）：直接调 ToolRegistry 里的本地函数
未来阶段（方案 B）：本地工具通过 MCP Server 暴露，远程工具走 HTTP/JSON-RPC

两层路由：
  1. server 路由 — tool 在本地 registry 还是远程 MCP server？
  2. 执行       — 本地直接调 func，远程发 HTTP 请求
"""

from tools.tool_register import ToolRegistry


class MCPClient:
    """
    统一工具调用入口。

    使用方式：
        registry = ToolRegistry()
        registry.register_function("bash", "...", {...}, run_bash)
        client = MCPClient(registry)
        result = client.call("bash", {"command": "ls"})
        # → {"status": "success", "tool": "bash", "result": "..."}
    """

    def __init__(self, registry: ToolRegistry = None):
        self.registry = registry or ToolRegistry()
        # 远程 MCP server 映射: tool_name → endpoint_url
        self._remote_servers: dict[str, str] = {}

    # ─── 注册远程服务 ────────────────────────────────
    def register_remote(self, tool_name: str, endpoint: str):
        """将某个工具指向远程 MCP server"""
        self._remote_servers[tool_name] = endpoint
        print(f"[mcp] 注册远程工具: {tool_name} → {endpoint}")

    # ─── 主入口 ──────────────────────────────────────
    def call(self, tool_name: str, params: dict) -> dict:
        """
        调用工具，返回统一格式：
          {"status": "success", "tool": "xxx", "result": "..."}
          {"status": "error",   "tool": "xxx", "message": "..."}
        """
        # 路由：远程优先，否则本地
        if tool_name in self._remote_servers:
            return self._call_remote(tool_name, params)

        return self._call_local(tool_name, params)

    # ─── 本地调用（当前阶段的核心路径）─────────────────
    def _call_local(self, tool_name: str, params: dict) -> dict:
        tool = self.registry.get(tool_name)
        if tool is None:
            available = [t["name"] for t in self.registry.list_tools()]
            return {
                "status": "error",
                "tool": tool_name,
                "message": f"工具 '{tool_name}' 未注册。可用工具: {available}",
            }

        try:
            result = tool.func(**params)
            return {"status": "success", "tool": tool_name, "result": result}
        except TypeError as e:
            return {
                "status": "error",
                "tool": tool_name,
                "message": f"参数不匹配: {e}\n期望: {tool.parameters}",
            }
        except Exception as e:
            return {"status": "error", "tool": tool_name, "message": str(e)}

    # ─── 远程调用（未来 MCP 协议）─────────────────────
    def _call_remote(self, tool_name: str, params: dict) -> dict:
        """通过 HTTP/JSON-RPC 调用远程 MCP server"""
        endpoint = self._remote_servers.get(tool_name)
        # TODO: 实现 JSON-RPC 调用
        return {
            "status": "error",
            "tool": tool_name,
            "message": f"远程调用尚未实现 (endpoint={endpoint})",
        }

    # ─── 辅助 ────────────────────────────────────────
    def list_tools(self) -> list[dict]:
        """返回所有可用工具的描述（给 Planner 用）"""
        tools = self.registry.list_tools()
        for t in tools:
            t["remote"] = t["name"] in self._remote_servers
        return tools
