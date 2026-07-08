import json
from llm.client import LLMClient


class Planner:
    """将自然语言任务拆解为可执行的步骤计划"""

    def __init__(self, llm: LLMClient):
        self.llm = llm

    def plan(self, task: str) -> list[dict]:
        """输入：自然语言任务
           输出：[{"step": "gaussian", "action": "opt", "params": {...}}, ...]
        """
        # ① 加载 prompt 模板
        prompt = self._load_prompt()

        # ② 把用户任务填进去
        filled_prompt = prompt.replace("{task}", task)

        # ③ 调 LLM
        raw_response = self.llm.generate(filled_prompt)

        # ④ 解析 LLM 返回的 JSON
        return self._parse_response(raw_response)

    def _load_prompt(self) -> str:
        """读取 planner 的 prompt 模板"""
        with open("agent/prompts/planner_prompt.txt", encoding="utf-8") as f:
            return f.read()

    def _parse_response(self, raw: str) -> list[dict]:
        """从 LLM 回复中提取 JSON 数组"""
        raw = raw.strip()

        # LLM 有时会在 JSON 外面包 markdown 代码块，先去掉
        if raw.startswith("```"):
            lines = raw.split("\n")
            raw = "\n".join(lines[1:-1])

        try:
            plan = json.loads(raw)
            if isinstance(plan, list):
                return plan
            # 如果 LLM 返回的是 {"steps": [...]} 这种对象
            if isinstance(plan, dict) and "steps" in plan:
                return plan["steps"]
        except json.JSONDecodeError:
            pass

        # 解析失败，返回空计划
        print(f"[Planner] 解析失败，LLM 返回: {raw[:200]}")
        return []
