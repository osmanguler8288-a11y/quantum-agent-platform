# 第三课：Planner — 让 LLM 拆任务

## 本课目标

- 理解 Agent 的第一个核心能力：任务分解
- 写出真正好用的 Planner prompt
- 让 LLM 输出结构化 JSON，而不是自然语言
- 把 Planner 和 Executor + MCPClient 串起来

## 前置要求

- 第二课完成（LLM Client 能调通）
- 理解 Python 的 `dict`、`list`、`str` 基本操作

---

## 3.1 Planner 在做什么

用户说一句自然语言：

> "优化乙醇的结构，然后计算 HOMO 能级"

Planner 要把它变成一个可执行计划：

```python
plan = [
    {"step": "gaussian", "action": "opt", "molecule": "ethanol",
     "method": "B3LYP", "basis": "6-31G(d)"},
    {"step": "gaussian", "action": "sp", "molecule": "ethanol",
     "method": "B3LYP", "basis": "6-31G(d)"},
    {"step": "multiwfn", "action": "homo", "molecule": "ethanol"},
]
```

关键要求：
1. **每个 step 要能直接执行**：包含工具名、操作、参数
2. **顺序要对**：先优化，再单点能，再分析
3. **输出是 JSON 数组**：程序能直接解析，不是自然语言

---

## 3.2 Prompt 工程：怎么写 Planner 的 system prompt

这是本课最重要的部分。差的 prompt 和好的 prompt 差距很大。

### 第一版：太模糊

```
你是一个计算化学助手。根据用户任务生成执行步骤。
```

**问题：** LLM 会写"建议你使用 Gaussian 优化乙醇结构..."这种自然语言，程序没法解析。

### 第二版：加了格式约束，但不够具体

```
你是一个计算化学助手。输出格式如下：
[{"step": "工具名", "params": {...}}]
```

**问题：** LLM 不知道有哪些工具、什么参数，会瞎编工具名。

### 第三版（好使的）：给齐全信息

打开 [agent/prompts/planner_prompt.txt](../agent/prompts/planner_prompt.txt)，改成下面这个：

```
你是量子化学计算平台的 Planner Agent。根据用户的任务描述，分解为可执行步骤。

## 可用工具
- gaussian：结构优化（opt）、单点能计算（sp）、频率分析（freq）
  参数：method（如 B3LYP, wB97XD）, basis（如 6-31G(d), def2-SVP）, charge, spin
- multiwfn：波函数分析
  参数：action（如 homo, lumo, bond_order, esp）
- eqv2：构象搜索
  参数：method, n_conformers

## 输出要求
1. 仅输出 JSON 数组，不要加任何解释文字
2. 每个元素包含：step（工具名）、action（操作名）、params（参数对象）
3. JSON 必须可直接被 json.loads() 解析
4. 步骤顺序必须符合计算逻辑（先优化 → 再单点能 → 再分析）

## 示例
用户："优化苯结构并计算HOMO"
输出：
[
  {"step": "gaussian", "action": "opt", "params": {"method": "B3LYP", "basis": "6-31G(d)", "charge": 0, "spin": 1, "molecule": "benzene"}},
  {"step": "gaussian", "action": "sp", "params": {"method": "B3LYP", "basis": "6-31G(d)", "charge": 0, "spin": 1, "molecule": "benzene"}},
  {"step": "multiwfn", "action": "homo", "params": {"molecule": "benzene"}}
]

## 用户任务
{task}
```

这个 prompt 有四个关键设计：
1. **工具白名单**：LLM 不会瞎编了
2. **明确输出格式**：JSON 数组，可直接解析
3. **few-shot 示例**：给了一个完整例子，LLM 会模仿
4. **约束条件**：顺序要对、格式要对

---

## 3.3 改造 agent/planner.py

打开 [agent/planner.py](../agent/planner.py)，当前是简化版。我们改成完整版：

```python
import json
from llm.client import LLMClient


class Planner:
    """将自然语言任务拆解为可执行的步骤计划"""

    def __init__(self, llm: LLMClient):
        self.llm = llm

    def plan(self, task: str) -> list[dict]:
        """输入：自然语言任务
           输出：[{"step": "gaussian", "action": "opt", "params": {...}}, ...]
        """
        # 1. 加载 prompt 模板
        prompt = self._load_prompt()

        # 2. 把用户任务填进去
        filled_prompt = prompt.replace("{task}", task)

        # 3. 调 LLM
        raw_response = self.llm.generate(filled_prompt)

        # 4. 解析 LLM 返回的 JSON
        return self._parse_response(raw_response)

    def _load_prompt(self) -> str:
        """读取 planner 的 prompt 模板"""
        with open("agent/prompts/planner_prompt.txt") as f:
            return f.read()

    def _parse_response(self, raw: str) -> list[dict]:
        """从 LLM 回复中提取 JSON 数组"""
        # LLM 有时会在 JSON 外面包 markdown 代码块，先去掉
        raw = raw.strip()
        if raw.startswith("```"):
            # 去掉 ```json 和结尾的 ```
            lines = raw.split("\n")
            raw = "\n".join(lines[1:-1])

        try:
            plan = json.loads(raw)
            if isinstance(plan, list):
                return plan
            # 如果 LLM 返回的是 {"steps": [...]} 这样的对象
            if isinstance(plan, dict) and "steps" in plan:
                return plan["steps"]
        except json.JSONDecodeError:
            pass

        # 解析失败，返回空计划
        print(f"[Planner] 解析失败，LLM 返回: {raw[:200]}")
        return []
```

**逐段讲解：**

`prompt.replace("{task}", task)`：简单替换。后面项目复杂了再改用 `PromptEngine`。

`raw.strip()`：去掉首尾空白和换行。这是 Python 操作字符串的常用方法。

```python
if raw.startswith("```"):
    lines = raw.split("\n")
    raw = "\n".join(lines[1:-1])
```

LLM 经常返回这种格式：

````
```json
[{"step": "gaussian", ...}]
```
````

`split("\n")` 按换行切 → `["```json", "[{...}]", "```"]`，`lines[1:-1]` 取中间那段 → `["[{...}]"]`，`"\n".join(...)` 拼回去。

`json.loads(raw)`：把 JSON 字符串转成 Python 对象。`loads` = "load string"。对应 `json.dumps()` = "dump to string"。

```python
try:
    plan = json.loads(raw)
except json.JSONDecodeError:
    plan = []
```

Python 的异常处理就是 `try...except`，Go 里是 `if err != nil`。Python 直接尝试，失败了走 except。这里不是不处理错误，而是"解析失败就返回空 plan，让上游决定怎么办"。

---

## 3.4 测试 Planner

写一个测试脚本验证 Planner 能不能正常工作：

```python
"""临时测试 Planner"""
from llm.client import LLMClient
from agent.planner import Planner

# 1. 创建 LLM Client
llm = LLMClient(model="qwen2.5:7b")

# 2. 创建 Planner
planner = Planner(llm)

# 3. 测试各种任务
test_tasks = [
    "优化乙醇的结构",
    "计算苯的HOMO-LUMO能隙",
    "搜索乙醇的最稳定构象",
]

for task in test_tasks:
    print(f"\n{'='*50}")
    print(f"任务: {task}")
    plan = planner.plan(task)
    print(f"计划: {plan}")
    print(f"共 {len(plan)} 步")

# 4. 验证计划合理性
for step in plan:
    assert "step" in step, f"缺少 step 字段: {step}"
    assert "action" in step, f"缺少 action 字段: {step}"
    assert "params" in step, f"缺少 params 字段: {step}"
print("\n所有计划格式正确！")
```

---

## 3.5 串通 Planner → Executor → MCPClient

现在把三个组件串起来。之前你的 [agent/executor.py](../agent/executor.py) 和 [agent/mcp_client.py](../agent/mcp_client.py) 已经修好了，我们验证一下能否串联：

```python
"""端到端测试：Planner → Executor → MCPClient"""
from llm.client import LLMClient
from agent.planner import Planner
from agent.executor import Executor
from agent.mcp_client import MCPClient


# 把 MCPClient 包装成工具注册表给 Executor
mcp = MCPClient()
tools = {
    "gaussian": mcp,
    "multiwfn": mcp,
    "eqv2": mcp,
}

# 创建各组件
llm = LLMClient(model="qwen2.5:7b")
planner = Planner(llm)
executor = Executor(tools)

# 执行全流程
task = "优化苯结构并计算HOMO"
print(f"用户任务: {task}")

plan = planner.plan(task)
print(f"Planner 拆解: {plan}")

result = executor.execute(plan, input_data={"molecule": "benzene"})
print(f"Executor 结果: {result}")
```

预期输出：

```
用户任务: 优化苯结构并计算HOMO
Planner 拆解: [{"step": "gaussian", ...}, {"step": "gaussian", ...}, {"step": "multiwfn", ...}]
[mcp call] tool = gaussian, params = {...}
[execute] step=gaussian, result=fake_result_from_gaussian
[mcp call] tool = gaussian, params = {...}
[execute] step=gaussian, result=fake_result_from_gaussian
[mcp call] tool = multiwfn, params = {...}
[execute] step=multiwfn, result=fake_result_from_multiwfn
Executor 结果: {...}
```

**这就是 Agent 闭环的核心链路。** Planner 拆任务 → Executor 巡回 MCPClient 调工具 → 返回结果。工具目前是 fake 的，但逻辑链路是完整的。

---

## 3.6 串起来以后，你项目里相关文件长什么样

`agent/planner.py` — 负责和 LLM 对话，拆任务
`agent/executor.py` — 负责遍历 plan，调工具
`agent/mcp_client.py` — 负责统一通信接口（现在返回 fake）

三者关系：

```
Planner.plan("优化苯")
    → 调 LLM
    → 返回 [{"step": "gaussian"}, {"step": "multiwfn"}]

Executor.execute(plan, input_data)
    → for step in plan:
    →     mcp_client.call(step["step"], step["params"])
    →     打印日志，收集结果
    → return 汇总结果
```

---

## 3.7 本课检查清单

- [ ] 能写出包含"工具列表 + 格式约束 + few-shot 示例"的 prompt
- [ ] Planner 能返回合法的 JSON 数组
- [ ] 能解释 `json.loads()` 和 `try...except` 的作用
- [ ] 能解释 `lines[1:-1]` 做了什么
- [ ] Planner → Executor → MCPClient 串通，终端看到完整日志输出
- [ ] 至少测了 3 个不同任务，Planner 都能拆出合理的步骤

---

## 3.8 常见问题

| 问题 | 原因 | 解决 |
|------|------|------|
| LLM 输出自然语言而不是 JSON | prompt 约束不够 | 加 "仅输出 JSON，不要加任何解释" 并在示例里强调 |
| JSON 解析失败 | LLM 在 JSON 外包了 markdown 代码块 | `_parse_response` 里已经处理了 ` ``` ` |
| Planner 拆出的步骤不合理 | prompt 里没说明工具能力 | 在 prompt 里详细列出每个工具的功能和参数 |
| plan 为空 | LLM 调不通或 prompt 太差 | 先单独测 `llm.generate()` 确认能通 |

---

下一课预告：第四课会加上 Critic（结果检查），然后第五课用 LangGraph 把三个 Agent 串成 DAG 自动流转。
