"""测试 Executor + State + MCPClient 联动（第四课）"""
from agent.mcp_client import MCPClient
from agent.executor import Executor
from agent.state import AgentState, TaskStatus

# 1. 创建 MCPClient 并注册工具
mcp = MCPClient()
mcp.register_server("gaussian", "local")
mcp.register_server("multiwfn", "local")
mcp.register_server("eqv2", "local")

# 2. 创建 Executor（最多重试 2 次）
executor = Executor(mcp, max_retries=2)

# 3. 模拟 Planner 已经拆好的 plan（跳过 Planner，直接测 Executor）
plan = [
    {"step": "gaussian", "action": "opt",
     "params": {"molecule": "ethanol", "method": "B3LYP", "basis": "6-31G(d)"}},
    {"step": "gaussian", "action": "sp",
     "params": {"molecule": "ethanol", "method": "B3LYP", "basis": "6-31G(d)"}},
    {"step": "multiwfn", "action": "homo",
     "params": {"molecule": "ethanol"}},
]

# 4. 创建 state — 这就是第四课的核心：用 state 承载整个任务
state = AgentState(task_id="test-001", user_query="优化乙醇并计算HOMO")
state.plan = plan

print(f"任务: {state.user_query}")
print(f"初始状态: {state.status.value}")
print(f"共 {len(state.plan)} 步\n")

# 5. 执行
state = executor.execute(state, input_data={"charge": 0, "spin": 1})

# 6. 验证结果
print(f"\n最终状态: {state.status.value}")
print(f"执行了 {len(state.results)} 步")
for r in state.results:
    step_num = r["step"]
    output = r.get("output", r.get("error", "unknown"))
    print(f"  step {step_num}: {output}")

# 7. 断言
assert state.status == TaskStatus.DONE, f"期望 DONE，实际 {state.status}"
assert len(state.results) == 3, f"期望 3 步结果，实际 {len(state.results)}"
assert state.current_step == 2, f"期望 current_step=2，实际 {state.current_step}"

print("\n全部断言通过！")
print("\n完整 state 快照:")
print(state.to_dict())
