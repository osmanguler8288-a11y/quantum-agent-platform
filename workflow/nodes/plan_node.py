def plan_node(state: dict) -> dict:
    """Plan node: decompose task into subtasks."""
    state["plan"] = state.get("plan", [])
    return state
