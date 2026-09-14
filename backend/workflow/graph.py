from langgraph.graph import StateGraph, END

from workflow.nodes.plan_node import make_plan_node
from workflow.nodes.exec_node import make_exec_node
from workflow.nodes.critique_node import make_critique_node
from workflow.nodes.rag_node import make_rag_node
from workflow.nodes.memory_node import make_memory_node
from app.utils.logger import logger

MAX_RETRIES = 3


def route_after_plan(state: dict) -> str:
    """plan 为空时（纯知识问答）直接结束，跳过执行"""
    plan = state.get("plan", [])
    if not plan:
        logger.info("[route] plan 为空 → END")
        return "end"
    logger.info("[route] plan 有 {} 步 → exec", len(plan))
    return "exec"


def route_after_critic(state: dict) -> str:
    """根据 critic 的 verdict 决定下一步"""
    verdict = state.get("verdict", {})
    retry = state.get("retry_count", 0)

    if verdict.get("passed"):
        logger.info("[route] critic 通过 → END")
        return "end"

    if retry >= MAX_RETRIES:
        logger.info("[route] retry={} >= {} → END", retry, MAX_RETRIES)
        return "end"

    logger.info("[route] critic 未通过, retry={} → exec", retry)
    return "exec"


def build_workflow(planner, executor, critic, retriever=None, memory_tool_getter=None):
    # 1. 用工厂函数创建节点
    memory_node = make_memory_node(memory_tool_getter) if memory_tool_getter else None
    rag_node = make_rag_node(retriever) if retriever else None
    plan_node = make_plan_node(planner)
    exec_node = make_exec_node(executor)
    critique_node = make_critique_node(critic)

    # 2. 构建 DAG
    graph = StateGraph(dict)

    if memory_node:
        graph.add_node("memory", memory_node)
    if rag_node:
        graph.add_node("rag", rag_node)
    graph.add_node("plan", plan_node)
    graph.add_node("exec", exec_node)
    graph.add_node("critic", critique_node)

    # 3. 入口 + 前置链：memory → rag → plan（按可用性灵活拼接）
    if memory_node:
        graph.set_entry_point("memory")
        if rag_node:
            graph.add_edge("memory", "rag")
        else:
            graph.add_edge("memory", "plan")
    elif rag_node:
        graph.set_entry_point("rag")
        graph.add_edge("rag", "plan")
    else:
        graph.set_entry_point("plan")

    graph.add_conditional_edges(
        "plan",
        route_after_plan,
        {
            "exec": "exec",
            "end": END,
        },
    )
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
