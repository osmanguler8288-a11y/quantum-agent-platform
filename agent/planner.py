import json
import re
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

        state.thinking, state.plan = self._parse_response(raw_response)
        return state

    def _load_prompt(self) -> str:
        with open("agent/prompts/planner_prompt.txt", encoding="utf-8") as f:
            return f.read()

    def _parse_response(self, raw: str) -> tuple[str, list[dict]]:
        raw = raw.strip()
        if raw.startswith("```"):
            lines = raw.split("\n")
            raw = "\n".join(lines[1:-1])

        start = raw.rfind("[")
        if start == -1:
            return raw, []

        thinking = raw[:start].strip()
        json_part = raw[start:]

        for end in (len(json_part), json_part.rfind("]") + 1):
            if end <= 0:
                continue
            try:
                plan = json.loads(json_part[:end])
                if isinstance(plan, list):
                    return thinking, plan
            except json.JSONDecodeError:
                continue

        return thinking, []

    def plan_stream(self, state: AgentState):
        state.transition(TaskStatus.PLANNING)
        prompt = self._load_prompt()
        filled_prompt = prompt.replace("{task}", state.user_query)

        full = ""
        json_start = None
        for token in self.llm.generate_stream(filled_prompt):
            full += token

            # 用正则检测 JSON 数组起始： [ 后跟可选换行/空白，再跟 {
            if json_start is None:
                m = re.search(r'\[[\n\s]*\{', full)
                if m:
                    json_start = m.start()

            # 只输出 JSON 之前的内容
            token_start = len(full) - len(token)
            if json_start is None:
                yield {"event": "thinking_chunk", "data": token}
            elif token_start + len(token) <= json_start:
                yield {"event": "thinking_chunk", "data": token}
            elif token_start < json_start:
                yield {"event": "thinking_chunk", "data": token[:json_start - token_start]}

        state.thinking, state.plan = self._parse_response(full)
        yield {"event": "plan_done", "data": state.plan}
