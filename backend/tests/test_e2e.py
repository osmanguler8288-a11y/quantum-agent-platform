"""端到端测试：Planner → Executor → MCPClient"""
from llm.client import LLMClient
from agent.planner import Planner
from agent.executor import Executor
from agent.mcp_client import MCPClient
from config.settings import settings

# 1. 创建 MCPClient，把同一个 client 注册为三个工具
mcp = MCPClient()
tools = {
    "gaussian": mcp,
    "multiwfn": mcp,
    "eqv2": mcp,
}

# 2. 创建各组件
llm = LLMClient(model=settings.LLM_MODEL)
planner = Planner(llm)
executor = Executor(tools)

# 3. 执行全流程
task = "优化苯结构并计算HOMO"
print(f"用户任务: {task}")
print()

plan = planner.plan(task)
print(f"Planner 拆解 ({len(plan)} 步):")
for i, step in enumerate(plan):
    print(f"  {i+1}. {step['step']} → {step['action']}")
print()

print("开始执行...")
print("-" * 40)
result = executor.execute(plan, input_data={"molecule": "benzene"})
print("-" * 40)
print()
print(f"最终结果: {result}")
