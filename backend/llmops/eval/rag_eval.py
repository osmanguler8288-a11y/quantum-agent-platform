def compute_recall(retrieved_ids: list[int], relevant_ids: list[int]) -> float:
    """召回率 = 找回的相关文档数 / 所有相关文档数"""
    if not relevant_ids:
        return 0.0
    return len(set(retrieved_ids) & set(relevant_ids)) / len(relevant_ids)


def compute_precision(retrieved_ids: list[int], relevant_ids: list[int]) -> float:
    """精确率 = 找回的相关文档数 / 找回的全部文档数"""
    if not retrieved_ids:
        return 0.0
    return len(set(retrieved_ids) & set(relevant_ids)) / len(retrieved_ids)


def compute_mrr(retrieved_ids: list[int], relevant_ids: list[int]) -> float:
    """Mean Reciprocal Rank —— 第一个相关文档排在第几位"""
    relevant_set = set(relevant_ids)
    for i, doc_id in enumerate(retrieved_ids, start=1):
        if doc_id in relevant_set:
            return 1.0 / i
    return 0.0


def evaluate_retrieval(retrieved: list[dict], relevant_ids: list[int]) -> dict:
    """对单次检索做完整评估"""
    retrieved_ids = [r.get("chunk_idx", -1) for r in retrieved]
    return {
        "recall": compute_recall(retrieved_ids, relevant_ids),
        "precision": compute_precision(retrieved_ids, relevant_ids),
        "mrr": compute_mrr(retrieved_ids, relevant_ids),
    }
