from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field


class MemoryItem(BaseModel):
    """一条记忆的统一数据结构"""
    id: Optional[str] = None              # Milvus 主键（auto_id 生成）
    user_id: str = "default_user"         # 多用户隔离
    memory_type: str = "working"          # working / episodic / semantic / perceptual
    content: str                          # 记忆文本（用于向量化）
    importance: float = 0.5               # 0.0 ~ 1.0
    timestamp: datetime = Field(default_factory=datetime.now)
    session_id: Optional[str] = None      # 关联会话
    metadata: Dict[str, Any] = {}         # 模态、来源、标签等
    embedding: Optional[list[float]] = None   # 向量（写入前填充）
    score: Optional[float] = None         # 检索相似度（仅检索后填充）


class MemoryConfig(BaseModel):
    """记忆模块配置"""
    milvus_collection: str = "agent_memories"
    embed_dim: int = 1024
    default_top_k: int = 5
    forget_threshold: float = 0.1         # 低于此重要性 → 遗忘
    consolidate_threshold: float = 0.7    # 高于此重要性 → 升级为长期
    max_age_days: int = 30                 # 超过此天数且低重要性 → 遗忘
    decay_half_life_days: float = 7.0      # 时效衰减半衰期
    enable_importance_self_eval: bool = True   # 写入时自动让 LLM 评重要性
