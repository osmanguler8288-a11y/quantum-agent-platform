from agent.executor import Executor
from agent.planner import Planner
from agent.state import AgentState,TaskStatus
from llm.client import LLMClient

def execute_stream(self,state:AgentState,input_data:dict=None):
    if input_data is None:
        input_data = {}
    state.transition(TaskStatus.EXECUTING)

    for i,step in enumerate(state.plan):
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

