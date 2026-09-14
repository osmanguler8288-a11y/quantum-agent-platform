from app.utils.logger import logger
def make_rag_node(retriever):
    def rag_node(state: dict) -> dict:
        query = state.get("user_query", "")

        if not query:
            state["context"] = ""
            return state

        context = retriever.retrieve_as_context(query)
        state["context"] = context
        logger.info("[rag] 检索到 {} 字符的参考资料", len(context))
        return state

    return rag_node
