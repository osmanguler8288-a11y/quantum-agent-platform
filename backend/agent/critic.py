import json
import re
from llm.client import LLMClient


class Critic:
    """检查计算结果，决定 pass 或 retry"""

    def __init__(self, llm: LLMClient):
        self.llm = llm

    def review(self, step: dict, result: dict, task: str = "") -> dict:
        """返回 {"passed": bool, "reason": str, "suggestions": str, "comment": str}"""
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
        with open("agent/prompts/critic_prompt.txt", encoding="utf-8") as f:
            return f.read()

    def _parse(self, raw: str) -> dict:
        """从 LLM 输出中提取最后一个 JSON 对象作为评审标签，前面的自然语言作为 comment"""
        text = raw.strip()
        # 去掉可能的 markdown 代码块包裹
        text = re.sub(r"^```[a-zA-Z]*\n", "", text)
        text = re.sub(r"\n```\s*$", "", text)

        # 尝试提取最后一个 {...} JSON 块（非贪婪，跨行）
        matches = list(re.finditer(r"\{[^{}]*?(?:\{[^{}]*?\}[^{}]*?)*\}", text, re.DOTALL))

        comment = text
        verdict = None
        if matches:
            json_str = matches[-1].group(0)
            # comment = JSON 之前的自然语言部分
            comment = text[:matches[-1].start()].strip()
            try:
                verdict = json.loads(json_str)
            except json.JSONDecodeError:
                verdict = None

        if verdict is None:
            # 完全没解析出 JSON，退化成关键词匹配
            raw_lower = text.lower()
            passed = "pass" in raw_lower or "correct" in raw_lower
            return {
                "passed": passed,
                "reason": text,
                "suggestions": "" if passed else "请重试",
                "comment": "",
            }

        return {
            "passed": bool(verdict.get("passed", False)),
            "reason": verdict.get("reason", ""),
            "suggestions": verdict.get("suggestions", ""),
            "comment": comment,
        }

