import json
from llm.client import LLMClient
from agent.state import AgentState, TaskStatus


class Planner:
    """将自然语言任务拆解为可执行的步骤计划"""

    def __init__(self, llm: LLMClient):
        self.llm = llm

    def plan(self, state: AgentState) -> AgentState:
        state.transition(TaskStatus.PLANNING)

        prompt = self._load_prompt()
        filled_prompt = prompt.replace("{task}", state.user_query)
        raw_response = self.llm.generate(filled_prompt)

        state.plan = self._parse_response(raw_response)
        return state

    def _load_prompt(self) -> str:
        with open("agent/prompts/planner_prompt.txt", encoding="utf-8") as f:
            return f.read()

    def _parse_response(self, raw: str) -> list[dict]:
        raw = raw.strip()
        if raw.startswith("```"):
            lines = raw.split("\n")
            raw = "\n".join(lines[1:-1])

        try:
            plan = json.loads(raw)
            if isinstance(plan, list):
                return plan
            if isinstance(plan, dict) and "steps" in plan:
                return plan["steps"]
        except json.JSONDecodeError:
            pass

        print(f"[Planner] 解析失败，LLM 返回: {raw[:200]}")
        return []
