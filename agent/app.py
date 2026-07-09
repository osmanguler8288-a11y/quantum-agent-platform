from agent.mcp_client import MCPClient
from agent.executor import Executor
from agent.planner import Planner
from agent.state import AgentState
from llm.client import LLMClient


def main():
    llm = LLMClient()
    mcp = MCPClient()
    planner = Planner(llm)
    executor = Executor(mcp)

    state = AgentState(task_id="task-001", user_query="优化一个Ni催化剂结构")

    state = planner.plan(state)
    state = executor.execute(state, {"mol": "Ni_cluster"})

    print("\n=== FINAL STATE ===")
    print(state.to_dict())


if __name__ == "__main__":
    main()
