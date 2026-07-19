def make_rag_node(retriever):
    def rag_node(state: dict) -> dict:
        query = state.get("user_query", "")

        if not query:
            state["context"] = ""
            return state

        context = retriever.retrieve_as_context(query)
        state["context"] = context
        print(f"[rag] 检索到 {len(context)} 字符的参考资料")
        return state

    return rag_node
