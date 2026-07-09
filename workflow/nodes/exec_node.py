def make_exec_node(executor):
    def exec_node(state: dict) -> dict:
        plan = state.get("plan", [])
        idx = state.get("current_step", 0)

        if idx >= len(plan):
            return state

        step = plan[idx]
        tool_name = step.get("step") or step.get("tool", "unknown")
        params = step.get("params", {})

        result = executor.mcp.call(tool_name, params)

        results = state.get("results", [])
        results.append({"step_idx": idx, "step": step, "result": result})
        state["results"] = results
        state["last_result"] = result

        print(f"[workflow] exec step={idx}: {tool_name}")
        return state
    return exec_node
