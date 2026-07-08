# 第二课：LLM Client 封装 + Prompt Engine

## 本课目标

- 理解 LLM Client 是什么，为什么要封装一层
- 用 OpenAI SDK 统一调用 Qwen / Ollama
- 学会 Prompt 模板：把变量塞进提示词
- 学会配置管理：用 YAML + 环境变量控制参数

## 前置要求

- 第一课完成（FastAPI 跑起来了）
- 装 Ollama：`brew install ollama` 并 `ollama pull qwen2.5:7b`（或其他模型）
- 装 Python 包：`pip3 install openai pyyaml`

---

## 2.1 LLM Client 为什么要封装

你以后会这样用 LLM：

```python
# Planner 要调 LLM
plan = llm.generate(planner_prompt, context=task)

# Critic 也要调 LLM
review = llm.generate(critic_prompt, context=result)
```

如果每次调都写一遍 `openai.OpenAI(...).chat.completions.create(...)`，代码会非常重复。封装一层的好处：

1. **统一接口**：不管底层是 Qwen、DeepSeek、GPT，上层代码不变
2. **统一配置**：base_url、api_key、temperature 只配一次
3. **方便以后加功能**：cache、日志、重试都在这层加

---

## 2.2 原理：OpenAI SDK 怎么跟任何模型对话

OpenAI SDK 本来是为 ChatGPT 写的，但大部分国产模型（Qwen、DeepSeek）都兼容了 OpenAI 的接口格式。Ollama 也提供了兼容端点。

```python
from openai import OpenAI

# ChatGPT
client = OpenAI(api_key="sk-xxx", base_url="https://api.openai.com/v1")

# Ollama 本地模型 — 把 base_url 指向 Ollama，api_key 随便填
client = OpenAI(api_key="ollama", base_url="http://localhost:11434/v1")
```

**调用的核心结构：**

```python
response = client.chat.completions.create(
    model="qwen2.5:7b",          # 模型名
    messages=[                    # 对话列表
        {"role": "system", "content": "你是化学专家"},
        {"role": "user", "content": "解释HOMO能级"},
    ],
    temperature=0.1,              # 0=稳定, 1=随机
    max_tokens=4096,              # 最大输出长度
)

# 拿回复文本
text = response.choices[0].message.content
```

**Go 程序员注意：** `response.choices[0]` 不是错误处理。LLM 响应几乎总是有 choice，如果出错会直接抛异常（`raise Exception`），不会返回空 choices。所以 Python 里习惯直接 `.choices[0]` 拿第一个。

---

## 2.3 改造你项目里的 `llm/client.py`

打开 [llm/client.py](../llm/client.py)，当前内容只是一个骨架。我们来实现它：

```python
from openai import OpenAI


class LLMClient:
    """LLM 调用的统一封装，兼容 OpenAI API 格式的模型"""

    def __init__(self, model: str = "qwen2.5:7b",
                 base_url: str = "http://localhost:11434/v1",
                 api_key: str = "ollama",
                 temperature: float = 0.1,
                 max_tokens: int = 4096):
        self.model = model
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.temperature = temperature
        self.max_tokens = max_tokens

    def generate(self, prompt: str, context: str = "") -> str:
        """发送 prompt，返回模型回复文本"""
        messages = []
        if context:
            messages.append({"role": "system", "content": context})
        messages.append({"role": "user", "content": prompt})

        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        return response.choices[0].message.content

    def chat(self, messages: list[dict]) -> str:
        """多轮对话"""
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        return response.choices[0].message.content
```

**逐行解释：**

`def __init__(self, model=..., base_url=..., ...)`：构造函数参数带默认值。Go 里没有默认参数，Python 里可以这样写。`model="qwen2.5:7b"` 表示不传就用这个默认值。

`self.client = OpenAI(api_key=api_key, base_url=base_url)`：`self.client` ≈ Go 里 `e.client`，实例化对象存成实例属性。

`response.choices[0].message.content`：整个调用链就是"拿第一个候选 → 拿消息体 → 拿文本"。

**测试一下（在项目根目录跑 python3）：**

```python
from llm.client import LLMClient

client = LLMClient(model="qwen2.5:7b")
reply = client.generate("用一句话解释什么是量子化学")
print(reply)
```

如果本地没装 Ollama，也可以配一个远程 API：

```python
client = LLMClient(
    model="deepseek-chat",
    base_url="https://api.deepseek.com/v1",
    api_key="你的key",
)
```

---

## 2.4 Prompt Engine：从"拼字符串"到"管模板"

现在还感受不到模板的必要。但当你有了 Planner prompt（50 行）、Critic prompt（30 行）以后，每次都拼 f-string 就乱了。

**思路：** 把 prompt 模板存成文件，用的时候读进来，填变量。

### 改造 `llm/prompt_engine.py`

```python
import os


class PromptEngine:
    """管理 prompt 模板：注册 → 渲染"""

    def __init__(self, templates_dir: str = ""):
        self.templates: dict[str, str] = {}
        self.templates_dir = templates_dir

    def register(self, name: str, template: str):
        """注册一个字符串模板"""
        self.templates[name] = template

    def load(self, name: str, filepath: str):
        """从文件加载模板并注册"""
        with open(filepath) as f:
            self.templates[name] = f.read()

    def render(self, name: str, **kwargs) -> str:
        """用变量填充模板。支持 Python 3.9 的 format()"""
        template = self.templates.get(name, "")
        if not template:
            raise ValueError(f"模板不存在: {name}")
        return template.format(**kwargs)
```

**`**kwargs` 是什么？** Go 里是 variadic `...`：

```go
// Go
func render(name string, kwargs ...string) string { ... }
render("planner", "task", "优化乙醇", "tool", "eqv2")
```

```python
# Python — **kwargs 是关键字可变参数，收成一个 dict
def render(self, name: str, **kwargs):
    print(kwargs)  # {"task": "优化乙醇", "tool": "eqv2"}

render("planner", task="优化乙醇", tool="eqv2")
```

`template.format(**kwargs)`：把 dict 拆开填进模板的 `{变量名}` 里。

### 用起来

在 `agent/prompts/` 下新建一个 `test_prompt.txt`：

```
你是{role}专家。任务：{task}。请用{language}回答。
```

然后测试：

```python
from llm.prompt_engine import PromptEngine

engine = PromptEngine()
engine.load("test", "agent/prompts/test_prompt.txt")
result = engine.render("test", role="量子化学", task="解释HOMO", language="中文")
print(result)
# 你是量子化学专家。任务：解释HOMO。请用中文回答。
```

---

## 2.5 配置管理：别把配置写死在代码里

你代码里到处是 `"http://localhost:11434/v1"`、`"qwen2.5:7b"` 这种魔法字符串。以后改一个要改十个文件。

**原则：** 配置集中管理，代码只读配置。

### YAML 配置文件

打开 [config/model_config.yaml](../config/model_config.yaml)，当前内容已经是模板了：

```yaml
models:
  default:
    name: qwen2.5:72b
    base_url: http://localhost:11434/v1
    max_tokens: 4096
    temperature: 0.1

  planner:
    name: qwen2.5:72b
    temperature: 0.0       # 规划任务希望输出稳定

  critic:
    name: qwen2.5:14b       # 检查结果可以用小模型省钱
    temperature: 0.1

  embedding:
    name: text-embedding-3-small
    dim: 1536
```

### Python 读 YAML

```python
import yaml

with open("config/model_config.yaml") as f:
    config = yaml.safe_load(f)

print(config["models"]["default"]["name"])  # qwen2.5:72b
```

### 环境变量方式

[config/settings.py](../config/settings.py) 里已经有了（不需要改）：

```python
import os

class Settings:
    LLM_MODEL = os.getenv("LLM_MODEL", "qwen2.5:72b")
    LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://localhost:11434/v1")

settings = Settings()
```

`os.getenv("LLM_MODEL", "qwen2.5:72b")`：先读环境变量 `LLM_MODEL`，没设置就用默认值 `"qwen2.5:72b"`。这样：
- 开发时用默认值
- 部署时 `export LLM_MODEL=deepseek-chat` 覆盖

---

## 2.6 动手：端到端测试 LLM Client

在项目根目录创建一个临时测试脚本 `test_llm.py`：

```python
"""临时测试 LLM Client，确认能跑后删掉"""
from llm.client import LLMClient
from llm.prompt_engine import PromptEngine

# 1. 测试 LLM 调用
client = LLMClient(model="qwen2.5:7b")
reply = client.generate("一句话解释什么是薛定谔方程")
print(f"LLM 回复: {reply}\n")

# 2. 测试 Prompt 模板
engine = PromptEngine()
engine.register("planner", "你是化学专家。任务：{task}。请列出步骤，用工具：{tools}")
result = engine.render("planner", task="优化乙醇结构", tools="gaussian, multiwfn")
print(f"渲染后的 prompt:\n{result}\n")

# 3. 组合使用：用模板渲染 prompt，再发给 LLM
prompt = engine.render("planner", task="计算苯的HOMO-LUMO能隙", tools="gaussian")
llm_reply = client.generate(prompt)
print(f"LLM 对模板 prompt 的回复:\n{llm_reply}")
```

跑一下：

```bash
cd /Users/Zhuanz/Documents/quantum-agent-platform
python3 test_llm.py
```

能跑通后把测试文件删了：`rm test_llm.py`

---

## 2.7 改造 LLM Router（多模型路由）

[llm/router.py](../llm/router.py) 当前是骨架。改造它：

```python
class LLMRouter:
    """根据任务类型路由到不同的 LLM 模型"""

    def __init__(self):
        self.clients: dict[str, object] = {}

    def register(self, name: str, client):
        """注册一个模型：router.register('planner', planner_llm)"""
        self.clients[name] = client

    def route(self, task_type: str):
        """获取模型；没注册就返回 default"""
        return self.clients.get(task_type, self.clients.get("default"))


# 使用示例
from llm.client import LLMClient

router = LLMRouter()
router.register("default", LLMClient(model="qwen2.5:7b"))
router.register("planner", LLMClient(model="qwen2.5:14b", temperature=0.0))
router.register("critic", LLMClient(model="qwen2.5:7b"))

# Planner 走大模型低温度，Critic 走小模型
planner_llm = router.route("planner")
critic_llm  = router.route("critic")
```

---

## 2.8 本课检查清单

- [ ] 能创建 `LLMClient` 实例，调 `generate()` 拿到 LLM 真实回复
- [ ] 能解释 `response.choices[0].message.content` 每部分是什么
- [ ] 能自己写一个 prompt 模板文件，用 `PromptEngine` 加载和渲染
- [ ] 能说清楚 `**kwargs` 和 `.format(**kwargs)` 做了什么
- [ ] 能配置两个不同模型，用 `LLMRouter` 按任务类型切换

---

## 2.9 常见报错

| 报错 | 原因 | 解决 |
|------|------|------|
| `Connection refused` | Ollama 没启动 | `ollama serve` 或 `ollama list` 确认 |
| `model not found` | 没 pull 模型 | `ollama pull qwen2.5:7b` |
| `KeyError: 'default'` | 没注册 default 就路由 | 先 `router.register("default", ...)` |
| `ValueError: 模板不存在` | 模板名写错了 | 检查 `register()` 或 `load()` 的名称 |
| `ImportError: No module named 'openai'` | 没装 | `pip3 install openai` |

---

下一课：[第三课：Planner — 让 LLM 拆任务](lesson-03-planner.md)
