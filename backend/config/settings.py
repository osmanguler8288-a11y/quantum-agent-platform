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
    # 小内存单机可用 Milvus Lite 文件；留空时仍连接独立 Milvus 服务。
    # MILVUS_URI 是 pymilvus ORM 的保留环境变量，只接受远程地址；
    # 本项目使用独立前缀，避免 SDK import 时把 Lite 文件路径误当 HTTP URI。
    MILVUS_URI = os.getenv("QAP_MILVUS_URI", "")

    # ---------- EqV2 31M 机器学习势函数服务 ----------
    # 远程推理服务（HTTP + Bearer Key），提供单点能/受力预测与异步几何优化。
    # ⚠️ 服务器只有 2 vCPU / 3.5 GB 且固定单 worker、单任务锁，并且 Nginx 做每 IP
    #    限流 —— 突发请求会被打成 503。客户端因此强制串行 + 退避重试，见
    #    tools/eqv2/client.py。切勿在这里调小重试次数来"提速"。
    EQV2_API_BASE_URL = os.getenv("EQV2_API_BASE_URL", "http://139.196.11.38:8888")
    EQV2_API_KEY = os.getenv("EQV2_API_KEY", "")
    # 单次 HTTP 请求超时。predict 实测约 0.2s，但服务忙时排队会久。
    EQV2_TIMEOUT = float(os.getenv("EQV2_TIMEOUT", "180.0"))
    # 优化作业的总预算（提交 + 轮询到终态）。实测水分子 200 步约 27s，
    # 但大分子/多步会显著更久，这里给足。
    EQV2_RELAX_TIMEOUT = float(os.getenv("EQV2_RELAX_TIMEOUT", "1800.0"))
    # 轮询间隔。文档建议 5~10s —— 比这更快只会撞上 Nginx 限流。
    EQV2_POLL_INTERVAL = float(os.getenv("EQV2_POLL_INTERVAL", "8.0"))
    # 409(模型忙)/429(队列满)/5xx 的最大重试次数
    EQV2_MAX_RETRIES = int(os.getenv("EQV2_MAX_RETRIES", "4"))
    # 服务端原子数上限。本地预检用，避免拿 422 当流程控制。
    EQV2_MAX_ATOMS = int(os.getenv("EQV2_MAX_ATOMS", "200"))
    # 优化产物目录（扩展 XYZ / 轨迹 CSV / 原始 JSON）
    EQV2_DATA_DIR = os.getenv(
        "EQV2_DATA_DIR",
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "eqv2"),
    )

    # ---------- 用户上传的分子结构附件 ----------
    # 用户在对话里上传的结构文件，解析成规范 XYZ 后落在这里，再把路径交给 Planner。
    # 与 EQV2_DATA_DIR 同理用 __file__ 推导绝对路径（仓库路径含中文，相对路径在
    # 部分 Windows code page 下会失败）。
    ATTACHMENT_DATA_DIR = os.getenv(
        "ATTACHMENT_DATA_DIR",
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "data", "attachments"),
    )
    # 附件文本上限（字节）。200 原子的 XYZ 约 8KB，1MB 给足余量，
    # 同时挡住误传的二进制/大文件。
    ATTACHMENT_MAX_BYTES = int(os.getenv("ATTACHMENT_MAX_BYTES", str(1024 * 1024)))

    # 原始波函数文件、描述符任务记录及下载缓存，与结构附件独立保存。
    DESCRIPTOR_DATA_DIR = os.getenv(
        "DESCRIPTOR_DATA_DIR",
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "descriptors"),
    )

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
