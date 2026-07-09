def make_rag_node(retriever=None):
    def rag_node(state: dict) -> dict:
        # RAG 节点暂时占位，Lesson 7 实现
        state["context"] = state.get("context", [])
        return state
    return rag_node
