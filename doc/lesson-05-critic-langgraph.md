# 第五课：Critic + LangGraph 工作流闭环

## 本课目标

- 实现 Critic Agent：让 LLM 检查计算结果是否合理
- 理解 LangGraph 的核心概念：StateGraph、Node、Edge、条件跳转
- 把 Planner → Executor → Critic 串成 DAG 自动流转
- 实现"结果不对 → 自动重试"的自纠错闭环

## 前置要求

- 第四课完成（Executor + State 能跑通）
- 安装 LangGraph：`pip3 install langgraph`

---

## 5.1 Critic 做什么

Executor 执行完了，结果对不对？LLM 不知道 Gaussian 的物理，但能判断：

- 能量数量级对不对？（分子总能量不该是 0.001 Hartree）
- 收敛了吗？（输出里有 "Normal termination" 吗？）
- 参数合理吗？（HOMO 能级在 -20 到 0 eV 之间？）

**Critic 不是取代人工检查，而是过滤明显错误，减少人工介入。**

---

## 5.2 Critic Prompt 设计

创建 [agent/prompts/critic_prompt.txt](../agent/prompts/critic_prompt.txt)（如果还没内容）：

```
你是量子化学计算结果的评审专家。检查计算结果是否有明显错误。

## 检查项目
1. 程序是否正常结束（gaussian 应有 "Normal termination"，multiwfn 不应有 "Error"）
2. 能量值数量级是否合理（分子总能量通常在 -10 ~ -10000 Hartree 范围）
3. HOMO/LUMO 值是否在物理合理范围（-20 ~ 10 eV）
4. 如果有 SCF 收敛信息，是否显示收敛（"converged"）

## 输出格式
仅输出 JSON 对象：
{"passed": true/false, "reason": "一句话原因", "suggestions": "如果失败，给出修复建议"}

用户任务：{task}
当前步骤：{current_step}
计算结果：
{result}
```

**为什么用 JSON 而不是自然语言？** 因为程序要解析。`passed: true/false` 决定是否重试。

---

## 5.3 改造 agent/critic.py

```python
import json
from llm.client import LLMClient


class Critic:
    """检查计算结果，决定 pass 或 retry"""

    def __init__(self, llm: LLMClient):
        self.llm = llm

    def review(self, step: dict, result: dict, task: str = "") -> dict:
        """返回 {"passed": bool, "reason": str, "suggestions": str}"""
        prompt = self._load_prompt()

        # 把变量填进 prompt
        filled = (
            prompt.replace("{task}", task)
                  .replace("{current_step}", str(step))
                  .replace("{result}", str(result))
        )

        raw = self.llm.generate(filled)
        return self._parse(raw)

    def _load_prompt(self) -> str:
        with open("agent/prompts/critic_prompt.txt") as f:
            return f.read()

    def _parse(self, raw: str) -> dict:
        raw = raw.strip()
        if raw.startswith("```"):
            lines = raw.split("\n")
            raw = "\n".join(lines[1:-1])

        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            # LLM 没按 JSON 格式输出，根据关键词判断
            raw_lower = raw.lower()
            if "pass" in raw_lower or "correct" in raw_lower:
                return {"passed": True, "reason": raw, "suggestions": ""}
            return {"passed": False, "reason": raw, "suggestions": "请重试"}
```

**关键逻辑：** 正常情况下 LLM 返回 `{"passed": true, ...}`，但如果 LLM 不听话返回了自然语言，我们就退化到关键词匹配（"pass" 出现了吗？）作为兜底。

---

## 5.4 LangGraph 是什么

LangGraph 的核心概念用 Go 类比：

```go
// Go — 如果用代码写状态机流转
func workflow(state State) State {
    state = planNode(state)      // 规划
    state = execNode(state)      // 执行
    state = criticNode(state)    // 检查
    if !state.Passed {
        state = execNode(state)  // 重试
    }
    return state
}
```

LangGraph 把这个流转声明成一张图（DAG）：

```python
from langgraph.graph import StateGraph, END

graph = StateGraph(dict)

graph.add_node("plan", plan_func)         # 注册节点
graph.add_node("exec", exec_func)
graph.add_node("critic", critic_func)

graph.set_entry_point("plan")              # 起始节点
graph.add_edge("plan", "exec")             # 固定边：plan 完去 exec
graph.add_edge("exec", "critic")           # 固定边：exec 完去 critic
graph.add_conditional_edges("critic", route, {  # 条件边
    "pass": END,   # 通过 → 结束
    "retry": "exec",  # 不通过 → 回 exec
})

app = graph.compile()
result = app.invoke({"task": "优化乙醇"})
```

节点函数签名统一：`def xxx(state: dict) -> dict`，接收 state dict，返回更新的 state dict。

---

## 5.5 改造 workflow/graph.py

打开 [workflow/graph.py](../workflow/graph.py)，改成完整版：

```python
from langgraph.graph import StateGraph, END
from agent.planner import Planner
from agent.executor import Executor
from agent.critic import Critic
from agent.state import AgentState, TaskStatus


def build_workflow(planner: Planner, executor: Executor, critic: Critic):
    """构建 LangGraph 工作流 DAG"""

    # --- 节点函数定义 ---

    def plan_node(state: dict) -> dict:
        """节点1：拆任务"""
        state["status"] = TaskStatus.PLANNING.value
        query = state.get("user_query", "")
        plan = planner.plan(query)
        state["plan"] = plan
        print(f"[workflow] plan: {len(plan)} steps")
        return state

    def exec_node(state: dict) -> dict:
        """节点2：执行当前步骤"""
        state["status"] = TaskStatus.EXECUTING.value

        plan = state.get("plan", [])
        idx = state.get("current_step", 0)
        if idx >= len(plan):
            state["status"] = TaskStatus.DONE.value
            return state

        step = plan[idx]
        result = executor.mcp.call(
            step.get("step", "unknown"),
            step.get("params", {}),
        )
        state.setdefault("results", []).append({
            "step_idx": idx,
            "step": step,
            "result": result,
        })
        state["last_result"] = result
        print(f"[workflow] exec step={idx}: {step.get('step')}")
        return state

    def critic_node(state: dict) -> dict:
        """节点3：检查结果"""
        state["status"] = TaskStatus.REVIEWING.value

        idx = state.get("current_step", 0)
        plan = state.get("plan", [])
        last = state.get("last_result", {})

        if idx < len(plan):
            review = critic.review(
                step=plan[idx],
                result=last,
                task=state.get("user_query", ""),
            )
            state["critic_passed"] = review.get("passed", True)
            print(f"[workflow] critic: passed={state['critic_passed']}")
        else:
            state["critic_passed"] = True

        return state

    def route_after_critic(state: dict) -> str:
        """根据 critic 结果决定下一步"""
        if state.get("critic_passed", True):
            # 当前步骤通过，前进到下一步
            state["current_step"] = state.get("current_step", 0) + 1
            plan = state.get("plan", [])
            if state["current_step"] >= len(plan):
                state["status"] = TaskStatus.DONE.value
                return "done"
            return "next"
        else:
            # 不通过，重试
            state["retry_count"] = state.get("retry_count", 0) + 1
            if state["retry_count"] >= 3:
                state["status"] = TaskStatus.FAILED.value
                return "done"
            return "retry"

    # --- 构建图 ---

    graph = StateGraph(dict)

    graph.add_node("plan", plan_node)
    graph.add_node("exec", exec_node)
    graph.add_node("critic", critic_node)

    graph.set_entry_point("plan")
    graph.add_edge("plan", "exec")
    graph.add_edge("exec", "critic")

    graph.add_conditional_edges(
        "critic",
        route_after_critic,
        {
            "next": "exec",   # 去下一步
            "retry": "exec",  # 重试当前步
            "done": END,      # 结束
        },
    )

    return graph.compile()
```

**逐段讲解：**

`state.setdefault("results", []).append(...)`：如果 `state` 里没有 `"results"` 这个 key，就设成空 list，然后在 list 末尾追加元素。等价于：

```python
if "results" not in state:
    state["results"] = []
state["results"].append(...)
```

`add_conditional_edges("critic", route_after_critic, {...})`：从 critic 节点出去后，调用 `route_after_critic` 函数，根据它返回的字符串从映射表里选目的地。

```
critic → route() → "next" → exec  # 下一步
                 → "retry" → exec # 重试
                 → "done"  → END  # 结束
```

---

## 5.6 改造 workflow/nodes/

四个 node 文件当前只是骨架。我们把上面的逻辑搬进去。

[workflow/nodes/plan_node.py](../workflow/nodes/plan_node.py)：

```python
def make_plan_node(planner):
    def plan_node(state: dict) -> dict:
        query = state.get("user_query", "")
        plan = planner.plan(query)
        state["plan"] = plan
        return state
    return plan_node
```

**`make_plan_node` 是什么？** 是一个工厂函数——返回一个闭包。因为 LangGraph 的 `add_node` 要求传一个 `fn(state) → state` 的函数，但我们的节点需要用到 planner 实例。所以用外层函数"注入" planner。

Go 程序员：这就是依赖注入的函数式写法。Go 里你可能会用 struct 方法：

```go
type PlanNode struct { planner *Planner }
func (n *PlanNode) Execute(state State) State { ... }
```

Python 里用闭包更简洁：

```python
# make_plan_node 接收 planner，返回一个"记住了 planner"的函数
plan_fn = make_plan_node(my_planner)
# plan_fn 可以直接当节点用了
result = plan_fn(state)
```

同理改造 [workflow/nodes/exec_node.py](../workflow/nodes/exec_node.py)：

```python
def make_exec_node(executor):
    def exec_node(state: dict) -> dict:
        plan = state.get("plan", [])
        idx = state.get("current_step", 0)
        if idx < len(plan):
            step = plan[idx]
            result = executor.mcp.call(
                step.get("step", "unknown"),
                step.get("params", {}),
            )
            state.setdefault("results", []).append(result)
            state["last_result"] = result
        return state
    return exec_node
```

[workflow/nodes/critique_node.py](../workflow/nodes/critique_node.py)：

```python
def make_critique_node(critic):
    def critique_node(state: dict) -> dict:
        plan = state.get("plan", [])
        idx = state.get("current_step", 0)
        last = state.get("last_result", {})

        if idx < len(plan):
            review = critic.review(
                step=plan[idx],
                result=last,
                task=state.get("user_query", ""),
            )
            state["critic_passed"] = review.get("passed", True)
        return state
    return critique_node
```

---

## 5.7 端到端测试

```python
"""测试完整 Agent 闭环"""
from llm.client import LLMClient
from agent.planner import Planner
from agent.executor import Executor
from agent.critic import Critic
from agent.mcp_client import MCPClient
from workflow.graph import build_workflow

# 1. 创建组件
llm = LLMClient(model="qwen2.5:7b")
planner = Planner(llm)
mcp = MCPClient()
executor = Executor(mcp)
critic = Critic(llm)

# 2. 构建工作流
app = build_workflow(planner, executor, critic)

# 3. 发起任务
result = app.invoke({
    "user_query": "优化苯结构并计算HOMO",
    "current_step": 0,
    "retry_count": 0,
})

print(f"\n最终状态: {result.get('status')}")
print(f"执行步骤数: {len(result.get('results', []))}")
print(f"重试次数: {result.get('retry_count', 0)}")
```

预期输出（fake 工具，critic 可能通过也可能不通过）：

```
[workflow] plan: 3 steps
[workflow] exec step=0: gaussian
[workflow] critic: passed=True
[workflow] exec step=1: gaussian
[workflow] critic: passed=True
[workflow] exec step=2: multiwfn
[workflow] critic: passed=True

最终状态: done
执行步骤数: 3
重试次数: 0
```

如果 critic 判断某步失败，会看到自动重试：

```
[workflow] critic: passed=False
[workflow] exec step=0: gaussian      ← 自动重试
[workflow] critic: passed=True
```

---

## 5.8 LangGraph 工作流全景图

```
                       ┌─────────┐
用户输入 ──────────────→│  plan   │ Planner 拆任务
                       └────┬────┘
                            │
                       ┌────▼────┐
                 ┌─────│  exec   │ Executor 执行当前步骤
                 │     └────┬────┘
                 │          │
                 │     ┌────▼────┐
                 │     │ critic  │ Critic 检查结果
                 │     └────┬────┘
                 │          │
                 │    ┌─────▼─────┐
                 │    │  route()  │ 条件判断
                 │    └─────┬─────┘
                 │          │
                 │   ┌──────┼──────┐
                 │   │      │      │
               retry  next  done   │
                 │   │      │      │
                 └───┘      │   ┌──▼──┐
                             │   │ END │ 结束
                             │   └─────┘
                             │
                    下一轮循环（i++）
```

**核心闭环：** Planner 只执行一次，Executor 和 Critic 形成循环——每一步都可能被退回重试。

---

## 5.9 本课检查清单

- [ ] Critic 能解析 LLM 输出，返回 `{"passed": bool, ...}` 的 dict
- [ ] 理解 LangGraph 的 node、edge、conditional_edges 三个概念
- [ ] graph.py 构建的 DAG 能跑通 plan → exec → critic → END
- [ ] critic 返回 False 时能自动回 exec 重试
- [ ] 能解释"工厂函数"（make_xxx_node）为什么这样设计
- [ ] 完整链路：用户输入一句话 → 返回所有步骤的执行结果

---

## 5.10 常见报错

| 报错 | 原因 | 解决 |
|------|------|------|
| `ImportError: No module named 'langgraph'` | 没装 | `pip3 install langgraph` |
| `graph.add_node() missing 1 required positional argument` | 签名变了 | 检查 LangGraph 版本，`add_node("name", func)` |
| 一直重试不停止 | critic 每次都返回 passed=false | 加 `retry_count >= 3` 兜底，直接标记失败 |
| `KeyError: 'plan'` | plan 节点没正确写入 state | 确认 plan_node 里有 `state["plan"] = plan` |

---

下一课：[第六课：真实工具接入 — subprocess 调量子化学程序](lesson-06-real-tools.md)
