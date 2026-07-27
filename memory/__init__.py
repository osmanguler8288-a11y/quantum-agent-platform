"""
记忆模块 — 为 Agent 提供短期/长期记忆能力

两层架构:
  manager.py  — MemoryManager: 基础设施层，管理多种记忆类型
  tool.py     — MemoryTool: 工具封装层，暴露为 Agent 可调用的工具
"""

from memory.manager import MemoryManager
from memory.tool import MemoryTool

__all__ = ["MemoryManager", "MemoryTool"]
