from openai import OpenAI
from config.settings import settings


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
    def console(self,messages:list[dict])->str:
        """支持多轮对话，直接传递完整的消息列表"""
        response = self.client.chat.completions.create(
            model = self.model,
            messages = messages,
            temperature = self.temperature,
            max_tokens = self.max_tokens
        )
        return response.choices[0].message.content
