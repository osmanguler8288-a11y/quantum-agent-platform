"""Memory 节点 — 在 plan 之前检索相关长期记忆，写入 state 供 planner 使用"""

from memory.tool import MemoryTool


def make_memory_node(memory_tool_getter):
    """
    memory_tool_getter: 一个函数，返回当前请求的 MemoryTool 实例
    （因为 MemoryTool 按 user_id 隔离，不能在图构建时固定）
    """
    def memory_node(state: dict) -> dict:
        query = state.get("user_query", "")
        user_id = state.get("user_id", "default_user")

        try:
            memory_tool = memory_tool_getter()
            if memory_tool is None:
                state["memory_context"] = ""
                return state

            # 检索 episodic + semantic 记忆
            results = memory_tool.memory_manager.retrieve_memories(
                query=query,
                limit=3,
                memory_types=["episodic", "semantic"],
                min_importance=0.3,
            )

            if results:
                lines = []
                for m in results:
                    lines.append(f"- [{m.memory_type}/{m.importance:.2f}] {m.content[:200]}")
                state["memory_context"] = "\n".join(lines)
                print(f"[memory-node] 召回 {len(results)} 条相关记忆")
            else:
                state["memory_context"] = ""
                print(f"[memory-node] 无相关历史记忆")
        except Exception as e:
            print(f"[memory-node] 检索失败: {e}")
            state["memory_context"] = ""

        return state
    return memory_node
