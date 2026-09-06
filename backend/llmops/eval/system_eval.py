def measure_latency(traces: list[dict]) -> dict:
    if not traces:
        return {"avg_ms": 0, "p95_ms": 0, "max_ms": 0}
    durations = sorted(t.get("duration_ms", 0) for t in traces)
    return {
        "avg_ms": sum(durations) / len(durations),
        "p95_ms": durations[int(len(durations) * 0.95)],
        "max_ms": durations[-1],
    }


def measure_cost(total_tokens: int, price_per_1k: float = 0.002) -> float:
    return total_tokens * price_per_1k / 1000
