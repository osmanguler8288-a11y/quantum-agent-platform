from agent.state import AgentState


def make_exec_node(executor):
    def exec_node(state: dict) -> dict:
        ag_state = AgentState(
            task_id=state.get("task_id", "unknown"),
            user_query=state.get("user_query", ""),
        )
        ag_state.plan = state.get("plan", [])
        ag_state.current_step = state.get("current_step", 0)

        ag_state = executor.execute(ag_state)

        state["status"] = ag_state.status.value
        state["results"] = ag_state.results
        state["current_step"] = ag_state.current_step
        state["retry_count"] = state.get("retry_count", 0)

        print(f"[workflow] exec: {len(ag_state.results)} results, status={ag_state.status.value}")
        return state
    return exec_node
