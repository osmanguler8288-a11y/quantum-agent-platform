from agent.mcp_client import MCPClient
from agent.executor import Executor
from agent.state import AgentState,TaskStatus

mcp = MCPClient()
executor = Executor(mcp,max_retries=2)

plan = [
    {"step": "gaussian", "action": "opt",
     "params": {"molecule": "ethanol", "method": "B3LYP", "basis": "6-31G(d)"}},
    {"step": "gaussian", "action": "sp",
     "params": {"molecule": "ethanol", "method": "B3LYP", "basis": "6-31G(d)"}},
    {"step": "multiwfn", "action": "homo",
     "params": {"molecule": "ethanol"}},
]
state = AgentState(task_id="test_001",user_query="优化乙醇结构")
state.plan = plan

state = executor.execute(state,input_data={"charge":0,"spin":1})
print(f"\n最终状态: {state.status.value}")
print(f"执行了 {len(state.results)} 步")
for r in state.results:
    step_num = r["step"]
    output = r.get("output", {})
    print(f"  step {step_num}: tool={output.get('tool')}, status={output.get('status')}")
