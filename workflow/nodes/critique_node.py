def make_critique_node(critic):
    def critique_node(state: dict) -> dict:
        plan = state.get("plan", [])
        idx = state.get("current_step", 0)
        last = state.get("last_result", {})

        if idx < len(plan):
            review = critic.review(
                step=plan[idx],
                result=last,
                task=state.get("user_query", ""),
            )
            passed = review.get("passed", True)
            state["critic_passed"] = passed

            if not passed:
                state["retry_count"] = state.get("retry_count", 0) + 1
                print(f"[workflow] critic: passed=False, retry={state['retry_count']}")
            else:
                print(f"[workflow] critic: passed=True")
        else:
            state["critic_passed"] = True

        return state
    return critique_node
