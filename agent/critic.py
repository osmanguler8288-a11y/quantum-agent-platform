import json
from llm.client import LLMClient


class Critic:
    """检查计算结果，决定 pass 或 retry"""

    def __init__(self, llm: LLMClient):
        self.llm = llm

    def review(self, step: dict, result: dict, task: str = "") -> dict:
        """返回 {"passed": bool, "reason": str, "suggestions": str}"""
        prompt = self._load_prompt()

        # 把变量填进 prompt
        filled = (
            prompt.replace("{task}", task)
                  .replace("{current_step}", str(step))
                  .replace("{result}", str(result))
        )

        raw = self.llm.generate(filled)
        return self._parse(raw)

    def _load_prompt(self) -> str:
        with open("agent/prompts/critic_prompt.txt") as f:
            return f.read()

    def _parse(self, raw: str) -> dict:
        raw = raw.strip()
        # 去掉可能的 markdown 代码块
        if raw.startswith("```"):
            lines = raw.split("\n")
            raw = "\n".join(lines[1:-1])

        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            # LLM 没按 JSON 输出，退化成关键词匹配
            raw_lower = raw.lower()
            if "pass" in raw_lower or "correct" in raw_lower:
                return {"passed": True, "reason": raw, "suggestions": ""}
            return {"passed": False, "reason": raw, "suggestions": "请重试"}

