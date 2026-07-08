from mcp_client import MCPClient
from tools.eqv2 import EqV2Tool
from executor import Executor
from planner import planner

def main():
    client = MCPClient()

    tools = {
        "eqv2": EqV2Tool(client)
    }

    executor = Executor(tools)

    query = "优化一个Ni催化剂结构"

    plan = planner(query)

    result = executor.execute(plan, {"mol": "Ni_cluster"})

    print("\nFINAL RESULT:")
    print(result)

if __name__ == "__main__":
    main()