class Executor:
    def __init__(self, tools: dict):
        self.tools = tools

    def execute(self, plan: list, input_data: dict):
        result = None
        for step in plan:
            tool_name = step.get("step") if isinstance(step, dict) else step
            if tool_name in self.tools:
                result = self.tools[tool_name].run(input_data)
                print(f"[execute] step={tool_name}, result={result}")
        return result
 
