from langgraph.graph import StateGraph, END
from workflow.nodes.plan_node import plan_node
from workflow.nodes.exec_node import exec_node
from workflow.nodes.critique_node import critique_node
from workflow.nodes.rag_node import rag_node


def build_workflow() -> StateGraph:
    graph = StateGraph(dict)

    graph.add_node("plan", plan_node)
    graph.add_node("exec", exec_node)
    graph.add_node("critique", critique_node)
    graph.add_node("rag", rag_node)

    graph.set_entry_point("plan")
    graph.add_edge("plan", "rag")
    graph.add_edge("rag", "exec")
    graph.add_edge("exec", "critique")
    graph.add_conditional_edges("critique", _route_critique, {
        "pass": END,
        "retry": "exec",
    })

    return graph.compile()


def _route_critique(state: dict) -> str:
    return "pass" if state.get("passed", False) else "retry"
