"""练习 1：测试 Executor 的重试逻辑（不用继承，纯基础写法）"""
from agent.executor import Executor
from agent.state import AgentState, TaskStatus


# 1. 写一个最简单的 fake 客户端 —— 跟 MCPClient 一样有 call() 方法
#    不需要继承，就是一个普通的类，你会写 Planner 就会写这个
class FakeTool:
    """模拟工具：normal_tool 正常，broken_tool 会崩溃"""

    def call(self, tool_name: str, params: dict) -> dict:
        if tool_name == "broken_tool":
            raise Exception("模拟工具崩溃：GPU 内存不足")
        # 正常工具返回 fake 结果
        print(f"[fake] call → {tool_name}")
        return {
            "status": "success",
            "tool": tool_name,
            "result": f"fake_result_from_{tool_name}",
        }


# 2. 创建对象
tools = FakeTool()
executor = Executor(tools, max_retries=3)

# 3. 构造 plan：3 步，第 2 步是 broken_tool
plan = [
    {"step": "gaussian", "action": "opt",
     "params": {"molecule": "ethanol"}},
    {"step": "broken_tool", "action": "crash",
     "params": {}},
    {"step": "multiwfn", "action": "homo",
     "params": {"molecule": "ethanol"}},
]

# 4. 创建 state
state = AgentState(task_id="test-001", user_query="测试重试")
state.plan = plan

print(f"任务: {state.user_query}")
print(f"最多重试: {executor.max_retries} 次\n")

# 5. 执行
state = executor.execute(state, input_data={})

# 6. 看结果
print(f"\n最终状态: {state.status.value}")
print(f"完成步数: {len(state.results)}")
for r in state.results:
    if "output" in r:
        print(f"  第 {r['step']} 步: OK")
    else:
        print(f"  第 {r['step']} 步: 失败 → {r['error']}")

assert state.status == TaskStatus.FAILED
assert len(state.results) == 2   # 只有前两步，第三步没执行
print("\n通过！")
