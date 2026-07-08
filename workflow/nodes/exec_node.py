def exec_node(state: dict) -> dict:
    """Execution node: run the current subtask."""
    state["results"] = state.get("results", [])
    return state
