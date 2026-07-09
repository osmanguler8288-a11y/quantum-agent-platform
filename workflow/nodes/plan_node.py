from agent.state import AgentState


def make_plan_node(planner):
    def plan_node(state: dict) -> dict:
        query = state.get("user_query", "")
        # 桥接 dict → AgentState → Planner → 取 plan 回 dict
        ag_state = AgentState(
            task_id=state.get("task_id", "unknown"),
            user_query=query,
        )
        ag_state = planner.plan(ag_state)
        state["plan"] = ag_state.plan
        print(f"[workflow] plan: {len(ag_state.plan)} steps")
        return state
    return plan_node
