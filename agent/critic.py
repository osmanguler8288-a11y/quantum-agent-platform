from llm.client import LLMClient


class Critic:
    def __init__(self, llm: LLMClient):
        self.llm = llm

    def review(self, result: dict, expected: dict = None) -> dict:
        """Review execution results and decide if retry is needed."""
        prompt = self._load_prompt("agent/prompts/critic_prompt.txt")
        response = self.llm.generate(prompt, context=str(result))
        return {"passed": "fail" not in response.lower(), "feedback": response}

    def _load_prompt(self, path: str) -> str:
        with open(path) as f:
            return f.read()
