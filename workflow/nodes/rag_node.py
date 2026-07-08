def rag_node(state: dict) -> dict:
    """RAG node: enrich plan with retrieved knowledge."""
    state["context"] = state.get("context", [])
    return state
