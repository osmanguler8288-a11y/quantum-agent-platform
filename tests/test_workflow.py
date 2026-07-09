"""测试完整 Agent 闭环：Planner → Executor → Critic → 自动重试"""
from llm.client import LLMClient
from agent.planner import Planner
from agent.executor import Executor
from agent.critic import Critic
from agent.mcp_client import MCPClient
from workflow.graph import build_workflow

# 1. 创建组件
llm = LLMClient()
planner = Planner(llm)
mcp = MCPClient()
executor = Executor(mcp)
critic = Critic(llm)

# 2. 构建工作流
app = build_workflow(planner, executor, critic)

# 3. 发起任务
result = app.invoke({
    "task_id": "e2e-001",
    "user_query": "优化苯结构并计算HOMO",
    "current_step": 0,
    "retry_count": 0,
})

# 4. 看结果
print(f"\n=== 最终结果 ===")
print(f"状态: {result.get('status')}")
print(f"执行步骤数: {len(result.get('results', []))}")
print(f"重试次数: {result.get('retry_count', 0)}")
for r in result.get("results", []):
    print(f"  step {r['step_idx']}: {r['result'].get('tool')} → {r['result'].get('status')}")
