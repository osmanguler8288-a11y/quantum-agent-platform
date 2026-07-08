class CostTracker:
    def __init__(self):
        self.total_tokens = 0
        self.total_time_ms = 0
        self.call_count = 0

    def record(self, tokens: int, latency_ms: float):
        self.total_tokens += tokens
        self.total_time_ms += latency_ms
        self.call_count += 1

    def summary(self) -> dict:
        return {
            "total_tokens": self.total_tokens,
            "total_time_ms": self.total_time_ms,
            "call_count": self.call_count,
            "avg_latency_ms": self.total_time_ms / max(self.call_count, 1),
        }
