import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    # LLM
    LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-chat")
    LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.deepseek.com")
    LLM_API_KEY = os.getenv("LLM_API_KEY", "")
    # 单次 LLM 请求超时（秒）。此前硬编码 15s，对推理模型（如 GLM-5.2）偏紧，
    # 是「服务内部异常」的高发来源。
    # 注意 openai-python 默认还会自动重试 2 次，超时属于可重试错误，
    # 所以最坏墙钟 ≈ LLM_TIMEOUT × 3。
    LLM_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "60.0"))

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

    # SQLite（工具库元数据 + 调用埋点）
    # 路径基于 __file__ 推导为绝对路径，不依赖 cwd —— 项目路径含中文，
    # 相对路径在某些 Windows code page 下会出现 "unable to open database file"。
    SQLITE_PATH = os.getenv(
        "SQLITE_PATH",
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "db", "qap.db"),
    )

    # 日志
    # ⚠️ LOG_DIR / LOG_LEVEL 由 app/utils/logger.py **直接读 os.getenv**，不经过 settings。
    #    原因是 logger 在 import 期就要完成配置，而 import 顺序不保证 settings 先执行。
    #    这里保留声明仅为「可用环境变量」的集中说明，便于查阅与写进 .env.example。
    # LOG_DIR：日志目录。留空则用「项目根 logs/」（基于 __file__ 推导）。
    #          容器部署（WORKDIR=/app）下没有仓库根，建议显式设为 /app/logs。
    # LOG_LEVEL：仅控制 stderr sink 级别（app-*.log 恒为 INFO，error.log 恒为 ERROR）。
    LOG_DIR = os.getenv("LOG_DIR", "")
    LOG_LEVEL = os.getenv("LOG_LEVEL", "DEBUG")


settings = Settings()
