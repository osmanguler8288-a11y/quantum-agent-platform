# LangGraph 由浅入深教学

> 本文档以本项目 [workflow/graph.py](../workflow/graph.py) 为最终范例，从最简单的 Hello World 讲起，逐步加难度，直到你完全看懂项目里的 DAG。

---

## 阅读顺序

1. [Level 1：什么是 LangGraph](#level-1什么是-langgraph)
2. [Level 2：第一个图 — 顺序执行](#level-2第一个图--顺序执行)
3. [Level 3：State 是什么](#level-3state-是什么)
4. [Level 4：条件路由 — if/else 也能图化](#level-4条件路由--ifelse-也能图化)
5. [Level 5：循环 — 让 Agent 自纠错](#level-5循环--让-agent-自纠错)
6. [Level 6：还原项目里的 graph.py](#level-6还原项目里的-graphpy)
7. [Level 7：常见坑](#level-7常见坑)
8. [速查表](#速查表)

---

## Level 1：什么是 LangGraph

**一句话**：把"一段业务流程"画成有向图（DAG），每个节点是个函数，节点之间用边连接，边可以是固定的也可以是带条件的。

### 核心三件套

| 概念 | 类比 | 代码 |
|------|------|------|
| **State（状态）** | 全局变量，所有节点都能读写 | `dict` 或 Pydantic Model |
| **Node（节点）** | 一个函数，输入 state，输出修改后的 state | `def node(state): return {...}` |
| **Edge（边）** | 节点之间的连线，可以是固定的或带条件的 | `graph.add_edge(A, B)` |

### 和普通函数调用的区别

```python
# 普通写法：流程写死在代码里
def pipeline():
    rag()
    plan = planner()
    if not plan:
        return
    while True:
        result = executor(plan)
        verdict = critic(result)
        if verdict.passed or retry >= 3:
            break

# LangGraph 写法：流程是"配置"出来的，可视化、可改
graph = StateGraph(dict)
graph.add_node("rag", rag_node)
graph.add_node("plan", plan_node)
graph.add_node("exec", exec_node)
graph.add_node("critic", critic_node)
graph.add_conditional_edges("plan", route_after_plan, {...})
graph.add_conditional_edges("critic", route_after_critic, {...})
app = graph.compile()
app.invoke({"user_query": "你好"})
```

**优势**：流程改动只需改图配置，不动节点函数本身；条件跳转、循环重试用统一的 API 表达。

---

## Level 2：第一个图 — 顺序执行

最简单的图：A → B → C，串行执行。

```python
from langgraph.graph import StateGraph, END

# 1. 定义节点（普通函数，输入 state，输出 dict）
def greet(state):
    print(f"[greet] 你好，{state.get('name', '陌生人')}")
    state["greeted"] = True
    return state

def ask(state):
    print(f"[ask] 今天想做什么？")
    state["asked"] = True
    return state

def bye(state):
    print(f"[bye] 再见，{state.get('name', '陌生人')}")
    return state

# 2. 建图
graph = StateGraph(dict)
graph.add_node("greet", greet)
graph.add_node("ask", ask)
graph.add_node("bye", bye)

# 3. 连边（固定边：A 执行完一定去 B）
graph.set_entry_point("greet")          # 起点
graph.add_edge("greet", "ask")
graph.add_edge("ask", "bye")
graph.add_edge("bye", END)              # 终点

# 4. 编译（必须 compile 才能用）
app = graph.compile()

# 5. 调用
result = app.invoke({"name": "小明"})
print(result)
# [greet] 你好，小明
# [ask] 今天想做什么？
# [bye] 再见，小明
# {'name': '小明', 'greeted': True, 'asked': True}
```

### 关键点

- **节点必须返回 dict**：返回值会被合并到 state 里（默认是覆盖式合并）
- **`set_entry_point`**：图的起点，必须有且只有一个
- **`END`**：特殊节点，表示流程结束
- **`compile()`**：图构建完不能直接调用，必须编译成可执行对象

---

## Level 3：State 是什么

State 是所有节点共享的"内存"。默认用 `dict`，也可以用 Pydantic 做类型约束。

### 默认行为：覆盖合并

```python
def node_a(state):
    return {"list_field": [1, 2]}  # 直接覆盖

def node_b(state):
    return {"list_field": [3, 4]}  # 又覆盖，结果是 [3, 4]

app.invoke({})
# state 变成 {"list_field": [3, 4]}
```

### 进阶：自定义 reducer（追加而不是覆盖）

如果你希望 list 字段追加而不是覆盖，需要用 `Annotated` 声明 reducer：

```python
from typing import Annotated
from operator import add

def reduce_list(left, right):
    # None 当空列表处理
    return (left or []) + (right or [])

class State(TypedDict):
    messages: Annotated[list, reduce_list]

graph = StateGraph(State)
# 现在 messages 字段会累加而不是覆盖
```

> **本项目用的是 `dict`，每个节点直接修改同一个 state dict 返回**，所以没有 reducer 问题。简单场景这样足够。

---

## Level 4：条件路由 — if/else 也能图化

固定边不够用——有时候要根据 state 决定下一步去哪。这就是**条件边**。

### 例子：根据用户是否登录，决定走欢迎流程还是登录流程

```python
def check_login(state):
    return state.get("logged_in", False)

def route_after_check(state) -> str:
    """路由函数：返回字符串，表示下一个节点名"""
    if check_login(state):
        return "welcome"
    return "login"

graph = StateGraph(dict)
graph.add_node("check", check_node)
graph.add_node("welcome", welcome_node)
graph.add_node("login", login_node)

graph.set_entry_point("check")

# 关键：条件边
graph.add_conditional_edges(
    "check",                    # 从哪个节点出发
    route_after_check,         # 路由函数
    {                          # 返回值 → 目标节点映射
        "welcome": "welcome",
        "login": "login",
    }
)

graph.add_edge("welcome", END)
graph.add_edge("login", END)

app = graph.compile()
app.invoke({"logged_in": True})   # → check → welcome → END
app.invoke({"logged_in": False})  # → check → login → END
```

### 路由函数的两个要点

1. **输入是 state**，输出是字符串（映射表里的 key）
2. **路由函数不能修改 state**（它是纯查询），改 state 必须在节点里改

### 对应到项目里

[workflow/graph.py:11-18](../workflow/graph.py#L11-L18)：

```python
def route_after_plan(state: dict) -> str:
    plan = state.get("plan", [])
    if not plan:
        return "end"     # 空计划直接结束
    return "exec"        # 有计划才执行
```

---

## Level 5：循环 — 让 Agent 自纠错

固定边 + 条件边能实现循环：`exec → critic → 如果不通过回到 exec`。

### 关键：条件边可以指向"前面的节点"

```python
def route_after_critic(state) -> str:
    verdict = state.get("verdict", {})
    retry = state.get("retry_count", 0)

    if verdict.get("passed"):
        return "end"          # 通过 → 结束
    if retry >= 3:
        return "end"          # 重试 3 次都不行 → 结束
    return "exec"             # 不通过 → 回到 exec 再来一次

graph.add_conditional_edges("critic", route_after_critic, {
    "exec": "exec",
    "end": END,
})
```

### 注意：必须有人改 retry_count，否则死循环

```python
def critique_node(state):
    verdict = critic.review(...)
    if not verdict.get("passed"):
        state["retry_count"] = state.get("retry_count", 0) + 1  # ← 这里改
    state["verdict"] = verdict
    return state
```

**这是 LangGraph 的硬约束**：路由函数是纯查询，**改 state 必须在节点里**。本项目 [workflow/nodes/critique_node.py:17-18](../workflow/nodes/critique_node.py#L17-L18) 就是这么做的。

---

## Level 6：还原项目里的 graph.py

把 Level 2-5 拼起来，你就看懂项目了。

### 完整流程图

```
        ┌──────┐
START → │ rag  │ （可选，没 retriever 就跳过）
        └───┬──┘
            ↓
        ┌───┴──┐
        │ plan │
        └───┬──┘
            ↓
       route_after_plan
       /             \  （条件边）
   plan 空            plan 非空
      ↓                 ↓
     END             ┌───┴──┐
                   │ exec  │ ←─────────┐
                   └───┬──┘            │
                       ↓               │
                   ┌───┴───┐          │
                   │ critic │          │
                   └───┬───┘            │
                       ↓               │
                  route_after_critic   │
                  /             \      │
              passed         not passed, retry < 3
                 ↓              ↓
                END  ───────────┘  （条件边，回到 exec）
```

### 对应代码 [workflow/graph.py:38-79](../workflow/graph.py#L38-L79)

```python
def build_workflow(planner, executor, critic, retriever=None):
    # 1. 工厂函数创建节点（注入依赖）
    rag_node = make_rag_node(retriever) if retriever else None
    plan_node = make_plan_node(planner)
    exec_node = make_exec_node(executor)
    critique_node = make_critique_node(critic)

    # 2. 建图
    graph = StateGraph(dict)

    # 3. 注册节点
    if rag_node:
        graph.add_node("rag", rag_node)
    graph.add_node("plan", plan_node)
    graph.add_node("exec", exec_node)
    graph.add_node("critic", critique_node)

    # 4. 起点 + 固定边
    if rag_node:
        graph.set_entry_point("rag")
        graph.add_edge("rag", "plan")
    else:
        graph.set_entry_point("plan")

    # 5. 条件边 1：plan 后空计划直接结束
    graph.add_conditional_edges("plan", route_after_plan, {
        "exec": "exec",
        "end": END,
    })

    # 6. 固定边：exec → critic
    graph.add_edge("exec", "critic")

    # 7. 条件边 2：critic 后通过/重试/失败
    graph.add_conditional_edges("critic", route_after_critic, {
        "exec": "exec",
        "end": END,
    })

    # 8. 编译
    return graph.compile()
```

### 为什么用工厂函数 `make_xxx_node`？

节点函数签名必须是 `(state) -> dict`，但你的 Planner/Executor/Critic 是带状态的实例。**工厂函数闭包**就是把实例"包"进节点函数里：

```python
def make_plan_node(planner):           # ← 接收实例
    def plan_node(state: dict):        # ← 节点函数签名
        ag_state = AgentState(...)
        planner.plan(ag_state)         # ← 闭包引用 planner
        state["plan"] = ag_state.plan
        return state
    return plan_node                    # ← 返回符合签名的节点函数
```

这样 LangGraph 看到的就是个普通 `(state) -> dict` 函数，但内部能用任何依赖。

---

## Level 7：常见坑

### 坑 1：路由函数不能改 state

```python
# ❌ 错误：路由函数里改 retry_count
def route(state):
    state["retry_count"] += 1   # 改了也不生效
    return "exec" if ... else "end"

# ✅ 正确：在节点里改
def critic_node(state):
    if not passed:
        state["retry_count"] = state.get("retry_count", 0) + 1
    return state
```

### 坑 2：节点忘记 return state

```python
# ❌ 错误：只改不返回
def bad_node(state):
    state["x"] = 1   # 改了但没 return

# ✅ 正确：必须 return
def good_node(state):
    state["x"] = 1
    return state
```

### 坑 3：忘记 compile

```python
# ❌ 直接 invoke StateGraph 会报错
graph = StateGraph(dict)
graph.add_node(...)
app.invoke({...})   # AttributeError

# ✅ compile 之后才能 invoke
app = graph.compile()
app.invoke({...})
```

### 坑 4：循环没有终止条件

```python
# ❌ 死循环：critic 永远不通过，永远回到 exec
def route_after_critic(state):
    return "exec" if not state["verdict"]["passed"] else "end"
# 必须加重试次数上限（项目里 MAX_RETRIES = 3）
```

### 坑 5：state 默认覆盖，list 字段需要 reducer

如果要累积 messages，要么用 `Annotated[list, add]` 声明 reducer，要么像项目里那样手动 list.append。

---

## 速查表

| 想做的事 | API |
|---------|-----|
| 创建图 | `StateGraph(dict)` 或 `StateGraph(PydanticModel)` |
| 注册节点 | `graph.add_node("name", fn)` |
| 设置起点 | `graph.set_entry_point("name")` |
| 固定边 | `graph.add_edge("A", "B")` |
| 条件边 | `graph.add_conditional_edges("A", router_fn, {key: target})` |
| 结束 | `graph.add_edge("X", END)` 或路由返回 `"end"` 映射到 `END` |
| 编译 | `graph.compile()` |
| 同步调用 | `app.invoke({...})` |
| 流式调用 | `app.stream({...})` 或 `app.astream({...})` |
| 获取中间状态 | `app.stream({...}, stream_mode="values")` 或 `"updates"` |

### 节点函数签名

```python
def node(state: dict) -> dict:
    # 读：x = state.get("x", default)
    # 改：state["y"] = ...
    return state
```

### 路由函数签名

```python
def router(state: dict) -> str:
    # 只读，不改
    if condition:
        return "key1"
    return "key2"
```

---

## 动手练习

1. **改项目里的 graph**：把 critic 节点删掉，改成 `plan → exec → END`，看看会发生什么
2. **加新节点**：在 plan 之前加一个 "memory" 节点，从 Redis 读取历史对话写入 state
3. **加分支**：如果 user_query 包含"画图"，路由到一个新的 "draw" 节点；否则走原流程

完成这三个练习，你就完全掌握 LangGraph 了。

---

## 进阶资源

- [LangGraph 官方文档](https://langchain-ai.github.io/langgraph/)
- [LangGraph GitHub 示例](https://github.com/langchain-ai/langgraph/tree/main/examples)
- 项目实例：[workflow/graph.py](../workflow/graph.py) + [workflow/nodes/](../workflow/nodes/)
