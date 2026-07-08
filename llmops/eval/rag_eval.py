def compute_recall(retrieved: list[str], relevant: list[str]) -> float:
    if not relevant:
        return 0.0
    return len(set(retrieved) & set(relevant)) / len(relevant)


def compute_mrr(retrieved: list[str], relevant: list[str]) -> float:
    for i, doc in enumerate(retrieved, start=1):
        if doc in relevant:
            return 1.0 / i
    return 0.0
