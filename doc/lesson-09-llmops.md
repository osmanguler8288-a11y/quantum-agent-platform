# 第九课：LLMOps — 日志、缓存、追踪、成本

## 本课目标

- 理解 LLMOps 的四根支柱：Log、Cache、Trace、Cost
- 让平台从"能用"变成"可观测、可调试、省钱"
- Redis 缓存：同样的计算不跑第二遍
- 全链路追踪：每一步耗时、输入输出可回放

## 前置要求

- 第八课完成（RAG + Agent 融合跑通）
- 安装：`pip3 install redis`（本节课可先用内存 dict 替代）

---

## 9.1 LLMOps 管什么

你的 Agent 跑起来以后，会遇到这些问题：

> "这个任务怎么跑了 30 分钟？卡在哪步了？"
> "同样的分子昨天算了，今天又算一遍，浪费 GPU"
> "这个月 LLM 调了 5000 次，花了多少钱？"

LLMOps 就是回答这些问题的：

| 模块 | 回答什么问题 | 对应文件 |
|------|-------------|---------|
| Logger | 每一步发生了什么？ | `llmops/logger.py` |
| Cache | 能不能不重复算？ | `llmops/cache.py` |
| Tracer | 慢在哪一步？ | `llmops/tracer.py` |
| Cost | 花了多少钱？ | `llmops/cost.py` |

---

## 9.2 Logger：全链路日志

当前你每个组件用 `print()` 打日志。问题：print 不持久化、没有时间戳、没法按 task_id 过滤。

改造 [llmops/logger.py](../llmops/logger.py)：

```python
import logging
import os
from datetime import datetime

# 确保日志目录存在
os.makedirs("logs", exist_ok=True)

# 创建专用 logger
logger = logging.getLogger("quantum_agent")
logger.setLevel(logging.DEBUG)

# 文件 handler — 持久化到文件
file_handler = logging.FileHandler("logs/agent.log")
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(logging.Formatter(
    "%(asctime)s | %(levelname)s | %(message)s"
))

# 控制台 handler — 开发和 debug
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter(
    "[%(levelname)s] %(message)s"
))

logger.addHandler(file_handler)
logger.addHandler(console_handler)


def log_llm_call(task_id: str, model: str, prompt: str,
                 response: str, latency_ms: float):
    """记录每次 LLM 调用"""
    logger.info(
        f"llm_call | task={task_id} | model={model} | "
        f"latency={latency_ms:.0f}ms | "
        f"prompt_len={len(prompt)} | response_len={len(response)}"
    )


def log_tool_call(task_id: str, tool: str, params: dict,
                  result_status: str, latency_ms: float):
    """记录每次工具调用"""
    logger.info(
        f"tool_call | task={task_id} | tool={tool} | "
        f"status={result_status} | latency={latency_ms:.0f}ms | "
        f"params={str(params)[:100]}"
    )


def log_agent_step(task_id: str, node: str, message: str):
    """记录 Agent 工作流节点"""
    logger.info(f"agent_step | task={task_id} | node={node} | {message}")


def log_error(task_id: str, component: str, error: str):
    """记录错误"""
    logger.error(f"error | task={task_id} | component={component} | {error}")
```

**Python logging 模块概念：**

- `Logger`：打日志的主体，可以有多个（`logger = logging.getLogger("quantum_agent")`）
- `Handler`：日志输出到哪里（文件、控制台、网络）
- `Formatter`：日志格式（时间 + 级别 + 消息）
- `Level`：DEBUG < INFO < WARNING < ERROR，只有 >= 当前级别的才会输出

Go 里你可能用 `logrus` 或 `zap`，概念一样：

```go
log.WithFields(log.Fields{
    "task_id": taskID,
    "model":   model,
}).Info("llm_call")
```

```python
logging.info(f"llm_call | task={task_id} | model={model}")
```

### 把 Logger 嵌入组件

在 Executor 里替换 print：

```python
# 之前
print(f"[execute] step={tool_name}, result={result}")

# 之后
from llmops.logger import log_tool_call
log_tool_call(state.task_id, tool_name, params, result.get("status"), latency_ms)
```

每个 LLM 调用、每次工具执行、每个工作流节点切换都用 logger 记录，出问题时你能看到完整的调用链。

---

## 9.3 Cache：Redis 缓存

**核心逻辑：** 调 LLM 或工具之前，先查"同样的输入上次算过吗？"

```
调 LLM(prompt="优化乙醇结构")
    ↓
计算 key = sha256(prompt + model)
    ↓
查 Redis → 命中！直接返回上次结果
         → 未命中 → 调 LLM → 结果存入 Redis
```

改造 [llmops/cache.py](../llmops/cache.py)：

```python
import hashlib
import json
import time


class Cache:
    """结果缓存。先用内存 dict，部署时换成 Redis"""

    def __init__(self, use_redis: bool = False,
                 redis_host: str = "localhost", redis_port: int = 6379):
        self.use_redis = use_redis
        self._memory_store: dict[str, dict] = {}

        if use_redis:
            import redis
            self._redis = redis.Redis(host=redis_host, port=redis_port)
        else:
            self._redis = None

    def make_key(self, prompt: str, model: str = "",
                 params: dict = None) -> str:
        """为同一个请求生成唯一 key"""
        raw = json.dumps({
            "prompt": prompt,
            "model": model,
            "params": params or {},
        }, sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def get(self, key: str) -> dict | None:
        """查缓存，返回 None 表示未命中"""
        if self._redis:
            raw = self._redis.get(key)
            if raw:
                return json.loads(raw)
            return None

        # 内存模式
        entry = self._memory_store.get(key)
        if entry is None:
            return None
        if time.time() > entry["expires_at"]:
            del self._memory_store[key]
            return None
        return entry["value"]

    def set(self, key: str, value: dict, ttl_seconds: int = 3600):
        """存缓存，默认 1 小时过期"""
        if self._redis:
            self._redis.setex(key, ttl_seconds, json.dumps(value))
            return

        # 内存模式
        self._memory_store[key] = {
            "value": value,
            "expires_at": time.time() + ttl_seconds,
        }

    def stats(self) -> dict:
        """缓存统计"""
        total = len(self._memory_store)
        return {"total_entries": total, "backend": "redis" if self._redis else "memory"}
```

**`hashlib.sha256(raw.encode()).hexdigest()[:16]`**：把任意长的请求参数哈希成 16 个字符的短 key。`[:16]` 是取前 16 个字符，因为缓存 key 不需要完整哈希。

**TTL（Time To Live）：** 缓存不过期就会越存越多，内存炸掉。设置 1 小时过期，确保"至少一小时内的重复请求不浪费钱"。

### 在 LLMClient 里加缓存

```python
class LLMClient:
    def __init__(self, ..., cache: Cache = None):
        ...
        self.cache = cache

    def generate(self, prompt: str, context: str = "") -> str:
        # 1. 先查缓存
        if self.cache:
            cache_key = self.cache.make_key(prompt, self.model)
            cached = self.cache.get(cache_key)
            if cached:
                print(f"[llm] cache hit! skipped API call")
                return cached["response"]

        # 2. 没命中，调 API
        response = self._call_api(prompt, context)

        # 3. 存入缓存
        if self.cache:
            self.cache.set(cache_key, {
                "response": response,
                "model": self.model,
            })

        return response
```

---

## 9.4 Tracer：执行追踪

Tracer 记录每一步的起止时间、输入输出，出问题可以回放。

改造 [llmops/tracer.py](../llmops/tracer.py)：

```python
import time
import json


class Tracer:
    """全链路执行追踪"""

    def __init__(self):
        self.traces: list[dict] = []

    def start_span(self, task_id: str, node: str, input_data: dict = None) -> str:
        """开始一个追踪 span，返回 span_id"""
        span_id = f"{task_id}_{node}_{int(time.time() * 1000)}"
        self.traces.append({
            "span_id": span_id,
            "task_id": task_id,
            "node": node,
            "start": time.time(),
            "end": None,
            "input": input_data or {},
            "output": None,
            "error": None,
        })
        return span_id

    def end_span(self, span_id: str, output_data: dict = None, error: str = None):
        """结束一个 span"""
        for t in self.traces:
            if t["span_id"] == span_id:
                t["end"] = time.time()
                t["duration_ms"] = (t["end"] - t["start"]) * 1000
                t["output"] = output_data or {}
                t["error"] = error
                return

    def get_timeline(self, task_id: str) -> list[dict]:
        """获取某个任务的时间线"""
        return sorted(
            [t for t in self.traces if t["task_id"] == task_id],
            key=lambda x: x["start"],
        )

    def summary(self, task_id: str = None) -> dict:
        """汇总统计"""
        traces = self.traces
        if task_id:
            traces = [t for t in traces if t["task_id"] == task_id]

        completed = [t for t in traces if t["end"] is not None]
        if not completed:
            return {"total_spans": len(traces), "completed": 0}

        durations = [t["duration_ms"] for t in completed]
        return {
            "total_spans": len(traces),
            "completed": len(completed),
            "total_duration_ms": sum(durations),
            "avg_duration_ms": sum(durations) / len(durations),
            "max_duration_ms": max(durations),
            "errors": sum(1 for t in completed if t.get("error")),
        }

    def export(self, filepath: str):
        """导出追踪数据为 JSON 文件，可离线分析"""
        with open(filepath, "w") as f:
            json.dump(self.traces, f, indent=2, ensure_ascii=False)
```

**`[t for t in self.traces if t["task_id"] == task_id]`**：列表推导式，过滤出指定 task_id 的 trace。Go 里要写循环 + append。

### 在工作流里插入 Trace

在 `graph.py` 的每个 node 函数里：

```python
def plan_node(state: dict) -> dict:
    task_id = state.get("task_id", "unknown")
    span_id = tracer.start_span(task_id, "plan", {"query": state.get("user_query")})

    try:
        plan = planner.plan(query, context=state.get("rag_context", ""))
        state["plan"] = plan
        tracer.end_span(span_id, {"plan": plan})
    except Exception as e:
        tracer.end_span(span_id, error=str(e))
        raise

    return state
```

这样每个节点的执行时间、输入输出都被记录，跑完可以 `tracer.export("logs/trace.json")` 导出分析。

---

## 9.5 Cost：成本统计

改造 [llmops/cost.py](../llmops/cost.py)：

```python
class CostTracker:
    """追踪 token 消耗和计算资源"""

    def __init__(self):
        self.llm_calls: list[dict] = []
        self.tool_calls: list[dict] = []

    def record_llm(self, model: str, prompt_tokens: int,
                   completion_tokens: int, latency_ms: float):
        """记录一次 LLM 调用"""
        self.llm_calls.append({
            "model": model,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "latency_ms": latency_ms,
        })

    def record_tool(self, tool: str, latency_ms: float):
        """记录一次工具调用（主要计 GPU 时间）"""
        self.tool_calls.append({"tool": tool, "latency_ms": latency_ms})

    def summary(self) -> dict:
        """成本汇总"""
        total_llm_tokens = sum(
            c["prompt_tokens"] + c["completion_tokens"] for c in self.llm_calls
        )
        total_llm_time = sum(c["latency_ms"] for c in self.llm_calls)
        total_tool_time = sum(c["latency_ms"] for c in self.tool_calls)

        return {
            "llm_calls": len(self.llm_calls),
            "total_llm_tokens": total_llm_tokens,
            "total_llm_time_ms": total_llm_time,
            "tool_calls": len(self.tool_calls),
            "total_tool_time_ms": total_tool_time,
            # 粗略成本估算（替换成你的实际价格）
            "estimated_llm_cost_usd": total_llm_tokens / 1e6 * 2.0,  # $2/M tokens
            "estimated_gpu_cost_usd": total_tool_time / 3600000 * 0.5,  # $0.5/GPU-hour
        }

    def report(self) -> str:
        """生成人类可读的报表"""
        s = self.summary()
        return (
            f"=== 成本报告 ===\n"
            f"LLM 调用: {s['llm_calls']} 次, {s['total_llm_tokens']} tokens, "
            f"{s['total_llm_time_ms']/1000:.0f}s\n"
            f"工具调用: {s['tool_calls']} 次, {s['total_tool_time_ms']/1000:.0f}s\n"
            f"预估 LLM 成本: ${s['estimated_llm_cost_usd']:.4f}\n"
            f"预估 GPU 成本: ${s['estimated_gpu_cost_usd']:.4f}"
        )
```

**`sum(c["prompt_tokens"] + ... for c in self.llm_calls)`**：生成器表达式 + sum()，Go 里是循环累加。

---

## 9.6 把四个组件串起来：LLMOps 初始化

新建一个统一的初始化入口：

```python
# llmops/__init__.py — 追加
from llmops.logger import logger, log_llm_call, log_tool_call, log_agent_step
from llmops.cache import Cache
from llmops.tracer import Tracer
from llmops.cost import CostTracker


class LLMOps:
    """LLMOps 统一入口"""

    def __init__(self):
        self.cache = Cache()
        self.tracer = Tracer()
        self.cost = CostTracker()

    def on_llm_call(self, task_id: str, model: str, prompt: str,
                    response: str, tokens: int, latency_ms: float):
        """统一钩子：LLM 调用后调用此方法"""
        log_llm_call(task_id, model, prompt, response, latency_ms)
        self.cost.record_llm(model, prompt_tokens=len(prompt)//4,
                             completion_tokens=len(response)//4,
                             latency_ms=latency_ms)

    def on_tool_call(self, task_id: str, tool: str, params: dict,
                     status: str, latency_ms: float):
        """统一钩子：工具调用后调用此方法"""
        log_tool_call(task_id, tool, params, status, latency_ms)
        self.cost.record_tool(tool, latency_ms)
```

之后在 Executor 和 LLMClient 里只需要调 `llmops.on_llm_call(...)` 和 `llmops.on_tool_call(...)`，日志、成本、追踪全部自动覆盖。

---

## 9.7 验证：跑一个任务，看日志和统计

```python
"""测试 LLMOps"""
from llmops import LLMOps
import time

ops = LLMOps()

# 模拟 LLM 调用
ops.on_llm_call(
    task_id="test-001", model="qwen2.5:7b",
    prompt="优化乙醇结构", response="Plan: [gaussian opt, ...]",
    tokens=200, latency_ms=1234,
)

# 模拟工具调用
ops.on_tool_call(
    task_id="test-001", tool="gaussian",
    params={"molecule": "ethanol"}, status="success", latency_ms=30000,
)

# 看统计
print(ops.cost.report())

# 看日志文件
import os
if os.path.exists("logs/agent.log"):
    with open("logs/agent.log") as f:
        for line in f.readlines()[-5:]:  # 只看最后5行
            print(line.strip())
```

---

## 9.8 本课检查清单

- [ ] Logger 能同时输出到文件和控制台
- [ ] Cache 能基于 prompt 生成 key，命中时跳过 LLM 调用
- [ ] Tracer 能记录每个节点的 start/end，export JSON 可回放
- [ ] CostTracker 能汇总 token 和 GPU 时间
- [ ] 理解 TTL 的作用——缓存为什么需要过期时间
- [ ] 能在 logs/agent.log 里看到结构化日志

---

## 9.9 常见报错

| 报错 | 原因 | 解决 |
|------|------|------|
| `ModuleNotFoundError: No module named 'redis'` | 没装 redis 包 | 先用 `use_redis=False` 走内存模式 |
| 缓存总是未命中 | key 生成逻辑包含时间戳等变化字段 | 确认 `make_key` 的输入是稳定的 |
| 日志文件不更新 | Python logging 默认有缓冲 | 加 `file_handler.flush()` 或在每个关键点调 `logger.handlers[0].flush()` |
| Trace span 的 duration 为负数 | end 的时钟和 start 不一致 | 用 `time.time()` 不要用 `time.clock()` |

---

下一课：[第十课：Evaluation + 全链路集成测试](lesson-10-evaluation.md)
