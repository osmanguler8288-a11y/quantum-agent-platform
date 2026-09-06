import time


class Tracer:
    def __init__(self):
        self.traces: list[dict] = []

    def start(self, name: str) -> str:
        trace_id = str(time.time_ns())
        self.traces.append({"id": trace_id, "name": name, "start": time.time(), "end": None})
        return trace_id

    def end(self, trace_id: str):
        for t in self.traces:
            if t["id"] == trace_id:
                t["end"] = time.time()
                t["duration_ms"] = (t["end"] - t["start"]) * 1000

    def summary(self) -> list[dict]:
        return [t for t in self.traces if t["end"] is not None]
