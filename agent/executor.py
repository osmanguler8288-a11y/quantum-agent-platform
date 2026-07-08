class Executor:
    """遍历 plan，调 MCPClient 执行每个步骤"""

    def __init__(self, tools: dict):
        self.tools = tools

    def execute(self, plan: list, input_data: dict = None):
        results = []
        for step in plan:
            tool_name = step.get("step") if isinstance(step, dict) else step
            action = step.get("action", "") if isinstance(step, dict) else ""
            params = step.get("params", {}) if isinstance(step, dict) else {}

            # 合并全局 input_data 和当前步骤的 params
            if input_data:
                params = {**input_data, **params}

            if tool_name in self.tools:
                result = self.tools[tool_name].call(tool_name, params)
                print(f"[execute] step={tool_name}, action={action}, result={result}")
                results.append(result)
            else:
                print(f"[execute] tool '{tool_name}' not found, skip")
        return results
