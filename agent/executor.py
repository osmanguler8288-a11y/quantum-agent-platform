from agent.state import AgentState, TaskStatus


class Executor:
    """遍历 plan，调用 MCPClient，处理失败重试"""

    def __init__(self, mcp_client, max_retries: int = 3):
        self.mcp = mcp_client
        self.max_retries = max_retries

    def execute(self, state: AgentState, input_data: dict = None) -> AgentState:
        """执行整个 plan，返回更新后的 state"""
        if input_data is None:
            input_data = {}

        state.transition(TaskStatus.EXECUTING)

        for i, step in enumerate(state.plan):
            state.current_step = i

            tool_name = self._get_tool_name(step)
            params = self._get_params(step, input_data)

            result = self._execute_with_retry(tool_name, params)

            if result["status"] == "error":
                state.results.append({"step": i, "error": result["message"]})
                state.transition(TaskStatus.FAILED)
                return state

            state.results.append({"step": i, "output": result})

        state.transition(TaskStatus.DONE)
        return state

    def _execute_with_retry(self, tool_name: str, params: dict) -> dict:
        """失败自动重试，最多 max_retries 次"""
        for attempt in range(1, self.max_retries + 1):
            try:
                result = self.mcp.call(tool_name, params)
                print(f"[execute] tool={tool_name}, attempt={attempt}, OK")
                return result
            except Exception as e:
                print(f"[execute] tool={tool_name}, attempt={attempt}, FAIL: {e}")

        return {"status": "error", "message": f"重试{self.max_retries}次全部失败"}

    def _get_tool_name(self, step) -> str:
        if isinstance(step, dict):
            return step.get("step") or step.get("tool", "unknown")
        return str(step)

    def _get_params(self, step, input_data: dict) -> dict:
        if isinstance(step, dict):
            return {**input_data, **step.get("params", {})}
        return input_data
