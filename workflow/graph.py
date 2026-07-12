from langgraph.graph import StateGraph, END

from workflow.nodes.plan_node import make_plan_node
from workflow.nodes.exec_node import make_exec_node
from workflow.nodes.critique_node import make_critique_node

MAX_RETRIES = 3


def route_after_critic(state: dict) -> str:
    """根据 critic 的 verdict 决定下一步"""
    verdict = state.get("verdict", {})
    retry = state.get("retry_count", 0)

    if verdict.get("passed"):
        print(f"[route] critic pass → END")
        return "end"

    if retry >= MAX_RETRIES:
        print(f"[route] retry={retry} >= {MAX_RETRIES} → END")
        return "end"

    print(f"[route] critic fail, retry={retry} → exec")
    return "exec"


def build_workflow(planner, executor, critic):
    # 1. 用工厂函数创建节点
    plan_node = make_plan_node(planner)
    exec_node = make_exec_node(executor)
    critique_node = make_critique_node(critic)

    # 2. 构建 DAG
    graph = StateGraph(dict)

    graph.add_node("plan", plan_node)
    graph.add_node("exec", exec_node)
    graph.add_node("critic", critique_node)

    graph.set_entry_point("plan")

    graph.add_edge("plan", "exec")
    graph.add_edge("exec", "critic")

    graph.add_conditional_edges(
        "critic",
        route_after_critic,
        {
            "exec": "exec",
            "end": END,
        },
    )

    return graph.compile()
