from openai import OpenAI
from config.settings import settings


class Embedder:
    """将文本转为向量，调用 OpenAI Embedding API"""

    def __init__(self, model: str = settings.EMBED_MODEL,
                 base_url: str = settings.EMBED_BASE_URL,
                 api_key: str = settings.EMBED_API_KEY):
        self.model = model
        # 允许传空字符串时 fallback 到 settings
        self.client = OpenAI(api_key=api_key or settings.EMBED_API_KEY,
                             base_url=base_url or settings.EMBED_BASE_URL)

    def embed(self, texts: list[str]) -> list[list[float]]:
        """
        批量将文本转为向量。
        输入: ["text1", "text2", ...]
        输出: [[0.023, -0.451, ...], [0.112, 0.789, ...]]
        """
        if not texts:
            return []

        # Embedding API 单次最多传 2048 条，这里先不做分批
        response = self.client.embeddings.create(
            model=self.model,
            input=texts,
        )
        # 按输入顺序返回，每个 data[i].embedding 是一个 float 列表
        return [item.embedding for item in response.data]

    def embed_query(self, query: str) -> list[float]:
        """
        把用户搜索的 query 转为向量（单条）。
        """
        result = self.embed([query])
        return result[0] if result else []
