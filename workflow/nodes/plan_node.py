from agent.state import AgentState


def make_plan_node(planner):
    def plan_node(state: dict) -> dict:
        query = state.get("user_query", "unknow")

        rag_context = state.get("context", "")
        history_text = state.get("history_text", "")
        parts = []
        if history_text:
            parts.append(f"## 对话历史\n{history_text}")
        if rag_context:
            parts.append(f"## 参考资料\n{rag_context}")
        full_context = "\n\n".join(parts)

        ag_state = AgentState(task_id=state.get("task_id", "unknow"), user_query=query)
        ag_state = planner.plan(ag_state, context=full_context)

        state["thinking"] = ag_state.thinking
        state["plan"] = ag_state.plan
        print(f"[workflow] plan: {len(ag_state.plan)} steps, thinking: {len(ag_state.thinking)} chars")
        return state
    return plan_node