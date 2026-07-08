class StateStore:
    def __init__(self):
        self._store: dict[str, dict] = {}

    def save(self, task_id: str, state: dict):
        self._store[task_id] = state

    def load(self, task_id: str) -> dict | None:
        return self._store.get(task_id)

    def delete(self, task_id: str):
        self._store.pop(task_id, None)

    def list_states(self) -> list[str]:
        return list(self._store.keys())
