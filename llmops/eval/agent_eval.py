def compute_success_rate(results: list[dict]) -> float:
    if not results:
        return 0.0
    passed = sum(1 for r in results if r.get("passed", False))
    return passed / len(results)


def compute_step_accuracy(plan: list[dict], executed: list[dict]) -> float:
    if not plan:
        return 0.0
    return len(executed) / len(plan)
