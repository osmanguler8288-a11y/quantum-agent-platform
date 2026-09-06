from llm.client import LLMClient
from agent.planner import Planner
from config.settings import settings

llm = LLMClient(model=settings.LLM_MODEL)
planner = Planner(llm)

test_tasks =[
    "计算乙醇的结构",
    "计算苯的HOMO-LUMO能隙",
    "搜索乙醇的最稳定构象",
]
# 3. 逐个测试
for task in test_tasks:
    print(f"\n{'='*50}")
    print(f"任务: {task}")

    plan = planner.plan(task)        # 调 Planner，不关心内部怎么做的
    print(f"计划: {plan}")
    print(f"共 {len(plan)} 步")

    # 4. 验证格式
    for step in plan:
        assert "step" in step, f"缺少 step 字段: {step}"
        assert "action" in step, f"缺少 action 字段: {step}"
        assert "params" in step, f"缺少 params 字段: {step}"

print("\nAll plan formats are correct!")