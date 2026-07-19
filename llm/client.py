from openai import OpenAI
from config.settings import settings

SYSTEM_PROMPT = """你是一个量子化学计算助手，专注于：
- 量子化学计算（ Gaussian、Multiwfn、构象搜索等）
- 分子结构分析、波函数分析、反应机理讨论
- 计算结果的解读与建议

回答要求：专业、准确，用中文交流。如果用户的问题超出量子化学范围，礼貌说明你的专长领域并尝试引导回正题。"""


class LLMClient:
    """LLM 调用的统一封装"""

    def __init__(self, model=settings.LLM_MODEL,
                 base_url=settings.LLM_BASE_URL,
                 api_key=settings.LLM_API_KEY,
                 temperature: float = 0.1,
                 max_tokens: int = 4096):
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.client = OpenAI(api_key=api_key, base_url=base_url)

    def generate(self, prompt: str, context: str = "") -> str:
        messages = []
        if context:
            messages.append({"role": "system", "content": context})
        messages.append({"role": "user", "content": prompt})

        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        return response.choices[0].message.content
    
    def generate_stream(self,prompt:str):
        """chunk 每个 token"""
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            stream=True,
        )
        for chunk in response:
            delta = chunk.choices[0].delta
            content = delta.content if hasattr(delta, 'content') else delta.get("content")
            if content:
                yield content
    def console(self, messages: list[dict], system_prompt: str = None) -> str:
        """支持多轮对话，自动在开头注入 system prompt 保证角色一致"""
        if system_prompt is None:
            system_prompt = SYSTEM_PROMPT
        full = [{"role": "system", "content": system_prompt}] + messages
        response = self.client.chat.completions.create(
            model=self.model,
            messages=full,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        return response.choices[0].message.content

    def console_stream(self, messages: list[dict], system_prompt: str = None):
        """流式多轮对话，逐 token yield"""
        if system_prompt is None:
            system_prompt = SYSTEM_PROMPT
        full = [{"role": "system", "content": system_prompt}] + messages
        response = self.client.chat.completions.create(
            model=self.model,
            messages=full,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            stream=True,
        )
        for chunk in response:
            delta = chunk.choices[0].delta
            content = delta.content if hasattr(delta, "content") else delta.get("content")
            if content:
                yield content
