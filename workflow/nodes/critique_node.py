def make_critique_node(critic):
    def critique_node(state: dict) -> dict:
        # 1. 取出当前步的 step 和 result
        current = state.get("current_step", 0)
        step = state.get("plan", [])[current] if state.get("plan") else {}
        results = state.get("results", [])
        result = results[-1] if results else {}

        # 2. 调 critic（小写 critic，是传入的实例）
        verdict = critic.review(
            step=step,
            result=result,
            task=state.get("user_query", ""),
        )

        # 3. 如果不通过，累加重试次数（必须在节点里改，路由函数改不动 state）
        if not verdict.get("passed"):
            state["retry_count"] = state.get("retry_count", 0) + 1

        # 4. 写回 state，供 graph.py 的路由函数读取
        state["verdict"] = verdict

        print(f"[workflow] critic: passed={verdict.get('passed')}, retry={state['retry_count']}")
        return state
    return critique_node
