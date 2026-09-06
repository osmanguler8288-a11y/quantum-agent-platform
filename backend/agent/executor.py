from agent.state import AgentState, TaskStatus


class Executor:
    """遍历 plan，按 type 分发：tool→MCPClient，reasoning→LLM"""

    def __init__(self, mcp_client, llm=None, max_retries: int = 3):
        self.mcp = mcp_client
        self.llm = llm
        self.max_retries = max_retries

    def execute(self, state: AgentState, input_data: dict = None) -> AgentState:
        if input_data is None:
            input_data = {}

        state.transition(TaskStatus.EXECUTING)

        for i, step in enumerate(state.plan):
            state.current_step = i
            step_type = step.get("type", "tool")

            if step_type == "reasoning":
                result = self._execute_reasoning(step, state)
            else:
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

    def execute_stream(self, state: AgentState, input_data: dict = None):
        """流式执行，每步开始/结束 yield 事件"""
        if input_data is None:
            input_data = {}

        state.transition(TaskStatus.EXECUTING)

        for i, step in enumerate(state.plan):
            state.current_step = i
            step_type = step.get("type", "tool")

            yield {"event": "step_start", "data": {"index": i, "step": step}}

            if step_type == "reasoning":
                result = self._execute_reasoning(step, state)
            else:
                tool_name = self._get_tool_name(step)
                params = self._get_params(step, input_data)
                result = self._execute_with_retry(tool_name, params)

            state.results.append({"step": i, "output": result})

            yield {"event": "step_done", "data": {"index": i, "result": result}}

            if result["status"] == "error":
                state.transition(TaskStatus.FAILED)
                return

        state.transition(TaskStatus.DONE)

    def _load_reasoning_prompt(self) -> str:
        with open("agent/prompts/reasoning_prompt.txt", encoding="utf-8") as f:
            return f.read()

    def _format_history_for_reasoning(self, history: list[dict]) -> str:
        """把 messages 列表转成纯文本，注入 reasoning prompt"""
        if not history:
            return "（无对话历史）"
        lines = []
        for m in history:
            role = "用户" if m["role"] == "user" else "助手"
            lines.append(f"{role}: {m['content']}")
        return "\n".join(lines)

    def _execute_reasoning(self, step: dict, state: AgentState) -> dict:
        if self.llm is None:
            return {"status": "success", "tool": "reasoning",
                    "result": f"跳过分析: {step.get('action', '')}"}

        prompt = self._load_reasoning_prompt()
        history_text = self._format_history_for_reasoning(state.history)
        filled = (
            prompt.replace("{task}", state.user_query)
                  .replace("{action}", step.get("action", ""))
                  .replace("{step_name}", step.get("step", ""))
                  .replace("{results}", str(state.results))
                  .replace("{history}", history_text)
        )
        try:
            response = self.llm.generate(filled)
            return {"status": "success", "tool": "reasoning",
                    "result": response}
        except Exception as e:
            return {"status": "error", "tool": "reasoning",
                    "message": str(e)}

    def _execute_with_retry(self, tool_name: str, params: dict) -> dict:
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
