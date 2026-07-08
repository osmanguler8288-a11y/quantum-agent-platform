# 第四课：Executor + MCPClient + State Machine

## 本课目标

- 让 Executor 能根据 plan 正确调度、容错、不跳过任何步骤
- 理解 MCPClient 的职责：统一通信接口，屏蔽工具差异
- 实现 AgentState 状态机，追踪任务流转
- 理解 Python 的异常处理（try/except/raise）和 Go 的 error 模式区别

## 前置要求

- 第三课完成（Planner 能拆出 JSON plan）
- 理解 `list[dict]` 的遍历和操作

---

## 4.1 三个组件各自管什么

先搞清楚职责边界：

```
Planner      — 跟 LLM 对话 → 产出 plan（只负责"想"）
Executor     — 遍历 plan → 调 MCPClient → 收集结果（只负责"调度"）
MCPClient    — 找到工具、建立连接、传参、返回结果（只负责"通信"）
AgentState   — 记录当前状态、步骤、重试次数（只负责"记"）
```

**Go 程序员注意：** Python 没有 interface 关键字，靠"鸭子类型"——只要对象有 `.call()` 方法，Executor 就能把它当 MCPClient 用。不需要显式声明 `implements MCPClient`。

---

## 4.2 Executor 改造：支持失败重试和状态追踪

我们当前 [agent/executor.py](../agent/executor.py) 只是最简单的遍历。这课把它改成一个健壮的调度器。

```python
from agent.state import AgentState, TaskStatus


class Executor:
    """遍历 plan，调用工具，收集结果，处理失败"""

    def __init__(self, mcp_client, max_retries: int = 3):
        self.mcp = mcp_client   # MCPClient 实例（统一通信接口）
        self.max_retries = max_retries

    def execute(self, state: AgentState, input_data: dict) -> AgentState:
        """执行整个 plan，返回更新后的 state"""
        state.transition(TaskStatus.EXECUTING)

        for i, step in enumerate(state.plan):
            state.current_step = i

            # 取工具名 — 兼容 step 是 dict 或 str
            tool_name = self._get_tool_name(step)
            params = self._get_params(step, input_data)

            # 带重试的执行
            result = self._execute_with_retry(tool_name, params)

            if result["status"] == "error":
                state.results.append({"step": i, "error": result["message"]})
                state.transition(TaskStatus.FAILED)
                return state

            state.results.append({"step": i, "output": result})

        state.transition(TaskStatus.DONE)
        return state

    def _execute_with_retry(self, tool_name: str, params: dict) -> dict:
        """调 MCPClient，失败自动重试"""
        last_error = None

        for attempt in range(1, self.max_retries + 1):
            try:
                result = self.mcp.call(tool_name, params)
                print(f"[execute] tool={tool_name}, attempt={attempt}, OK")
                return result
            except Exception as e:
                last_error = str(e)
                print(f"[execute] tool={tool_name}, attempt={attempt}, FAIL: {e}")

        return {"status": "error", "message": last_error}

    def _get_tool_name(self, step) -> str:
        """从 step 提取工具名 — 兼容多种格式"""
        if isinstance(step, dict):
            return step.get("step") or step.get("tool", "unknown")
        return str(step)

    def _get_params(self, step, input_data: dict) -> dict:
        """合并 step 参数和全局 input_data"""
        if isinstance(step, dict):
            return {**input_data, **step.get("params", {})}
        return input_data
```

**逐段讲解：**

`state.transition(TaskStatus.EXECUTING)`：状态机换状态。Go 里你可能会 `e.state = StateExecuting`，Python 封装进方法里（方便以后加日志、校验）。

`enumerate(state.plan)`：同时拿 index 和值。
```python
for i, step in enumerate(["a", "b", "c"]):
    print(i, step)
# 0 a
# 1 b
# 2 c
```

`{**input_data, **step.get("params", {})}`：字典合并。`**` 是把 dict 拆开：
```python
a = {"x": 1, "y": 2}
b = {"y": 99, "z": 3}
merged = {**a, **b}
# merged = {"x": 1, "y": 99, "z": 3}
# 后面的 b 覆盖前面的 a（同名 key）
```

`try...except Exception as e`：Python 的错误处理。全部代码如下：

```python
try:
    result = self.mcp.call(tool_name, params)
except Exception as e:
    # call() 抛异常了，这里捕获
    last_error = str(e)
```

`Exception` 是所有异常的基类。这里捕获一切异常，不让单个工具失败搞崩整个平台。Go 里的等价写法：

```go
result, err := e.mcp.Call(toolName, params)
if err != nil {
    lastError = err.Error()
}
```

---

## 4.3 MCPClient：统一通信接口

[agent/mcp_client.py](../agent/mcp_client.py) 当前返回 fake 结果。本课把它设计成有扩展能力的接口：

```python
class MCPClient:
    """MCP 协议客户端：统一调用外部工具"""

    def __init__(self):
        self.servers: dict[str, str] = {}
        # server 配置示例：{"gaussian": "http://gpu-node:8080", "eqv2": "local"}

    def register_server(self, tool_name: str, endpoint: str):
        """注册某个工具对应的 MCP server 地址"""
        self.servers[tool_name] = endpoint

    def call(self, tool_name: str, params: dict) -> dict:
        """
        统一调用入口：
        1. 查配置，找到 tool_name 对应哪个 server
        2. 建立连接，发送请求
        3. 返回结果 / 抛异常
        """
        server = self.servers.get(tool_name, "local")

        if server == "local":
            return self._call_local(tool_name, params)
        else:
            return self._call_remote(server, tool_name, params)

    def _call_local(self, tool_name: str, params: dict) -> dict:
        """本地调用（目前 fake，第六课替换成 subprocess）"""
        print(f"[mcp] local call → {tool_name}, params={params}")
        return {
            "status": "success",
            "tool": tool_name,
            "result": f"fake_result_from_{tool_name}",
        }

    def _call_remote(self, server: str, tool_name: str, params: dict) -> dict:
        """远程 HTTP 调用（以后实现）"""
        # TODO: requests.post(f"{server}/tools/{tool_name}", json=params)
        raise NotImplementedError(f"远程调用未实现: {server}")
```

**`raise NotImplementedError(...)`** ≈ Go 的 `panic("not implemented")`，但这个更温和——明确告诉调用者"这个功能还没做"。

---

## 4.4 AgentState：状态机追踪任务流转

[agent/state.py](../agent/state.py) 你已经有了，这课加深理解。

```python
from enum import Enum


class TaskStatus(str, Enum):
    PENDING = "pending"
    PLANNING = "planning"
    EXECUTING = "executing"
    REVIEWING = "reviewing"
    RETRYING = "retrying"
    DONE = "done"
    FAILED = "failed"


class AgentState:
    def __init__(self, task_id: str, user_query: str = ""):
        self.task_id = task_id
        self.user_query = user_query
        self.status = TaskStatus.PENDING
        self.plan: list[dict] = []
        self.current_step: int = 0
        self.results: list[dict] = []
        self.retry_count: int = 0
        self.final_result: str = ""

    def transition(self, new_status: TaskStatus):
        """状态流转，后续可以在这里加日志"""
        old = self.status
        self.status = new_status
        print(f"[state] {old.value} → {new_status.value}")

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "status": self.status.value,
            "current_step": self.current_step,
            "total_steps": len(self.plan),
            "retry_count": self.retry_count,
            "final_result": self.final_result,
        }
```

**状态流转图（下一课用 LangGraph 自动化）：**

```
PENDING → PLANNING → EXECUTING → REVIEWING → DONE
                         ↑            │
                         └── RETRYING ← (fail)
                              │
                           FAILED (重试超限)
```

`str, Enum` 继承：`TaskStatus.DONE.value` 返回 `"done"`，比直接用字符串安全——写 `TaskStatus.DONE` 不会打错字。

---

## 4.5 串联测试

```python
"""测试 Executor + State + MCPClient 联动"""
from agent.mcp_client import MCPClient
from agent.executor import Executor
from agent.state import AgentState, TaskStatus

# 1. 准备
mcp = MCPClient()
executor = Executor(mcp, max_retries=2)

# 2. 模拟 Planner 已经拆好的 plan
plan = [
    {"step": "gaussian", "action": "opt",
     "params": {"molecule": "ethanol", "method": "B3LYP", "basis": "6-31G(d)"}},
    {"step": "gaussian", "action": "sp",
     "params": {"molecule": "ethanol", "method": "B3LYP", "basis": "6-31G(d)"}},
    {"step": "multiwfn", "action": "homo",
     "params": {"molecule": "ethanol"}},
]

# 3. 创建 state
state = AgentState(task_id="test-001", user_query="优化乙醇并算HOMO")
state.plan = plan

# 4. 执行
state = executor.execute(state, input_data={"charge": 0, "spin": 1})

# 5. 看结果
print(f"\n最终状态: {state.status.value}")
print(f"执行了 {len(state.results)} 步")
for r in state.results:
    print(f"  step {r['step']}: {r.get('output', r.get('error'))}")
```

预期输出（fake 结果）：

```
[state] pending → executing
[mcp] local call → gaussian, params={...}
[execute] tool=gaussian, attempt=1, OK
[mcp] local call → gaussian, params={...}
[execute] tool=gaussian, attempt=1, OK
[mcp] local call → multiwfn, params={...}
[execute] tool=multiwfn, attempt=1, OK
[state] executing → done

最终状态: done
执行了 3 步
  step 0: {'status': 'success', 'tool': 'gaussian', 'result': 'fake_result_from_gaussian'}
  step 1: {'status': 'success', 'tool': 'gaussian', 'result': 'fake_result_from_gaussian'}
  step 2: {'status': 'success', 'tool': 'multiwfn', 'result': 'fake_result_from_multiwfn'}
```

---

## 4.6 Go ↔ Python 异常处理对比

```go
// Go — 显式返回 error，每个调用都要检查
result, err := doSomething()
if err != nil {
    return fmt.Errorf("failed: %w", err)
}
// 继续用 result
```

```python
# Python — 直接执行，出错用 try/except 兜住
try:
    result = do_something()
    # 继续用 result
except Exception as e:
    print(f"failed: {e}")
    # 处理错误
```

Python 哲学：大胆写，出错了再说。Go 哲学：每一步都想清楚出错怎么办。

**最佳实践：**
- 在 MCPClient 里让错误"冒上去"（raise），别吞掉
- 在 Executor 里统一 try/except，决定重试还是跳过去

---

## 4.7 本课检查清单

- [ ] Executor 能遍历 plan，每步都调 MCPClient
- [ ] 失败步骤能重试（最多 max_retries 次）
- [ ] 状态机在节点开始/结束/失败时正确流转
- [ ] task_id 全程追踪，results 数组记录每步结果
- [ ] 能解释 `{**a, **b}` 字典合并做了什么
- [ ] 能解释 `try/except` 和 Go `if err != nil` 的区别
- [ ] 写脚本测了 3 步 plan + 1 步故意失败，检查重试逻辑

---

## 4.8 常见报错

| 报错 | 原因 | 解决 |
|------|------|------|
| `AttributeError: 'dict' object has no attribute 'call'` | Executor 传的 mcp_client 不是对象而是 dict | 检查 `Executor(mcp_client)` 传入的是 MCPClient 实例 |
| `KeyError: 'step'` | step dict 里没有 "step" 字段 | 用 `step.get("step", "unknown")` 做安全访问 |
| 重试但每次还是失败 | MCPClient.call 没抛异常而是返回了 error dict | 检查 fake 返回的 status 是不是 "success" |

---

下一课：[第五课：Critic + LangGraph 工作流闭环](lesson-05-critic-langgraph.md)
