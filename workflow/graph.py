from langgraph.graph import StateGraph, END
from workflow.nodes.plan_node import make_plan_node
from workflow.nodes.exec_node import make_exec_node
from workflow.nodes.critique_node import make_critique_node


def build_workflow(planner, executor, critic):
    """构建 LangGraph 工作流 DAG"""

    plan_fn = make_plan_node(planner)
    exec_fn = make_exec_node(executor)
    critic_fn = make_critique_node(critic)

    def route_after_critic(state: dict) -> str:
        """只读 state，返回方向。state 的修改在节点里做。"""
        if state.get("critic_passed", True):
            # 通过：前进到下一步
            state["current_step"] = state.get("current_step", 0) + 1
            if state["current_step"] >= len(state.get("plan", [])):
                state["status"] = "done"
                return "done"
            return "next"
        else:
            # 不通过：检查重试上限
            if state.get("retry_count", 0) >= 3:
                state["status"] = "failed"
                return "done"
            return "retry"

    graph = StateGraph(dict)

    graph.add_node("plan", plan_fn)
    graph.add_node("exec", exec_fn)
    graph.add_node("critic", critic_fn)

    graph.set_entry_point("plan")
    graph.add_edge("plan", "exec")
    graph.add_edge("exec", "critic")

    graph.add_conditional_edges(
        "critic",
        route_after_critic,
        {
            "next": "exec",
            "retry": "exec",
            "done": END,
        },
    )

    return graph.compile()
