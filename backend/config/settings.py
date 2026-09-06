import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    # LLM
    LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-chat")
    LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.deepseek.com")
    LLM_API_KEY = os.getenv("LLM_API_KEY", "")

    # Embedding
    EMBED_MODEL = os.getenv("EMBED_MODEL", "text-embedding-3-small")
    EMBED_BASE_URL = os.getenv("EMBED_BASE_URL", "https://api.openai.com/v1")
    EMBED_API_KEY = os.getenv("EMBED_API_KEY", "")
    EMBED_DIM = int(os.getenv("EMBED_DIM", "1024"))  # text-embedding-3-small 输出 1024 维

    # Redis
    REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))

    # Milvus
    MILVUS_HOST = os.getenv("MILVUS_HOST", "localhost")
    MILVUS_PORT = int(os.getenv("MILVUS_PORT", "19530"))

    # RAG
    CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "512"))
    CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "50"))
    TOP_K = int(os.getenv("TOP_K", "5"))

    # Agent
    MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))
    MAX_STEPS = int(os.getenv("MAX_STEPS", "20"))


settings = Settings()
