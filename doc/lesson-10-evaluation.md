# 第十课：Evaluation + 全链路集成测试

## 本课目标

- 用量化指标评估系统好坏（而不是"看着还行"）
- 写 pytest 单元测试和集成测试
- 构建评估数据集，跑 benchmark
- 理解 Agent 评估的思路：不是测"对错"，而是测"成功率"

## 前置要求

- 第九课完成（LLMOps 就位）
- 安装：`pip3 install pytest`

---

## 10.1 评估什么

你的平台有多个环节，每个环节评估方式不同：

| 环节 | 评估什么 | 指标 |
|------|---------|------|
| Planner | 拆出的计划合理吗？ | Step Accuracy（拆对了几步） |
| RAG | 检索到的资料相关吗？ | Recall@K、MRR |
| Agent 整体 | 任务最终成功了吗？ | Success Rate |
| 系统 | 快不快？贵不贵？ | Latency p95、Cost per task |

---

## 10.2 RAG 评估：Recall@K + MRR

[llmops/eval/rag_eval.py](../llmops/eval/rag_eval.py) 已有骨架，完善它：

```python
from typing import Optional


def evaluate_rag(retriever, test_queries: list[dict]) -> dict:
    """在测试集上评估 RAG 系统

    test_queries 格式：
    [
      {"query": "过渡态用什么泛函？",
       "relevant_docs": ["过渡态计算推荐使用 B3LYP"]},
      ...
    ]
    """
    recalls = []
    mrrs = []

    for item in test_queries:
        results = retriever.retrieve(item["query"], top_k=5)

        # 因为是假 embedding（哈希），我们用文本包含判断相关性
        retrieved_texts = [r["text"] for r in results]
        relevant_set = item["relevant_docs"]

        # 判断哪些检索到的文档是相关的
        relevant_retrieved = []
        for rt in retrieved_texts:
            is_relevant = any(
                rel in rt for rel in relevant_set
            )
            relevant_retrieved.append(is_relevant)

        # Recall@5
        recall = sum(relevant_retrieved) / max(len(relevant_set), 1)
        recalls.append(recall)

        # MRR
        mrr = 0.0
        for i, is_rel in enumerate(relevant_retrieved, start=1):
            if is_rel:
                mrr = 1.0 / i
                break
        mrrs.append(mrr)

    return {
        "num_queries": len(test_queries),
        "recall@5_avg": sum(recalls) / max(len(recalls), 1),
        "mrr_avg": sum(mrrs) / max(len(mrrs), 1),
    }
```

**`any(rel in rt for rel in relevant_set)`**：判断检索到的文本里是否包含任一相关文档的关键词。`any()` 是 Python 内置函数，只要有一个 True 就返回 True。

```python
# any 示例
any([False, False, True])  # True
any([False, False])        # False

# 可以用在任何可迭代对象上
any(x > 0 for x in [-1, 0, 2])  # True（生成器表达式）
```

---

## 10.3 Agent 评估：Success Rate

[llmops/eval/agent_eval.py](../llmops/eval/agent_eval.py)：

```python
def evaluate_agent(workflow_app, test_cases: list[dict]) -> dict:
    """在测试集上评估 Agent

    test_cases 格式：
    [
      {"query": "优化苯结构", "expected_steps": ["gaussian opt"]},
      {"query": "计算HOMO", "expected_steps": ["gaussian sp", "multiwfn"]},
    ]
    """
    passed = 0
    details = []

    for case in test_cases:
        result = workflow_app.invoke({
            "user_query": case["query"],
            "current_step": 0,
            "retry_count": 0,
        })

        plan = result.get("plan", [])
        plan_actions = [s.get("action", "") for s in plan]

        # 判断：plan 里是否包含了所有 expected_steps
        all_found = all(
            expected in " ".join(plan_actions)
            for expected in case["expected_steps"]
        )

        details.append({
            "query": case["query"],
            "passed": all_found,
            "plan": plan,
            "status": result.get("status"),
        })

        if all_found:
            passed += 1

    return {
        "total": len(test_cases),
        "passed": passed,
        "success_rate": passed / max(len(test_cases), 1),
        "details": details,
    }
```

**注意：** Agent 评估跟传统单元测试不同。传统测试断言 `result == expected`，这里断言的是"plan 是否包含关键步骤"。因为同一个任务可能有多种合理方案——拆 3 步和拆 5 步都可能对。

---

## 10.4 系统评估：Latency + Cost

[llmops/eval/system_eval.py](../llmops/eval/system_eval.py)：

```python
import time


def benchmark_latency(workflow_app, test_queries: list[str],
                      runs_per_query: int = 3) -> dict:
    """测量端到端延迟"""
    all_latencies = []

    for query in test_queries:
        for run in range(runs_per_query):
            start = time.time()
            workflow_app.invoke({
                "user_query": query,
                "current_step": 0,
                "retry_count": 0,
            })
            elapsed_ms = (time.time() - start) * 1000
            all_latencies.append(elapsed_ms)

    sorted_lat = sorted(all_latencies)
    n = len(sorted_lat)

    return {
        "num_runs": n,
        "avg_ms": sum(sorted_lat) / n,
        "p50_ms": sorted_lat[int(n * 0.5)],
        "p95_ms": sorted_lat[int(n * 0.95)],
        "p99_ms": sorted_lat[int(n * 0.99)],
        "min_ms": sorted_lat[0],
        "max_ms": sorted_lat[-1],
    }


def evaluate_cost_efficiency(cost_tracker, num_tasks: int) -> dict:
    """每任务成本"""
    s = cost_tracker.summary()
    return {
        "avg_llm_calls_per_task": s["llm_calls"] / max(num_tasks, 1),
        "avg_llm_time_ms_per_task": s["total_llm_time_ms"] / max(num_tasks, 1),
        "est_cost_per_task_usd": (
            s["estimated_llm_cost_usd"] + s["estimated_gpu_cost_usd"]
        ) / max(num_tasks, 1),
    }
```

**p50、p95、p99 是什么？** 

- p50 = 中位数：一半请求比这个快
- p95 = 第 95 百分位：95% 请求比这个快，剩下 5% 更慢
- p99 = 你几乎不会超过的值

为什么要看 p95 而不是平均值？如果 99 个请求 1 秒完成，1 个请求 100 秒完成，平均值是 ~2 秒——看起来还行。但 p95 会告诉你"那个 100 秒的请求严重拉胯"。

---

## 10.5 pytest 单元测试

你 `tests/` 目录里已有三个文件，现在填肉。

### test_agent.py

```python
import pytest
from agent.state import AgentState, TaskStatus


class TestAgentState:
    """测试状态机"""

    def test_initial_state(self):
        state = AgentState(task_id="test-001")
        assert state.status == TaskStatus.PENDING
        assert state.current_step == 0
        assert state.plan == []

    def test_transition(self):
        state = AgentState(task_id="test-001")
        state.transition(TaskStatus.EXECUTING)
        assert state.status == TaskStatus.EXECUTING

    def test_to_dict(self):
        state = AgentState(task_id="test-001")
        d = state.to_dict()
        assert d["task_id"] == "test-001"
        assert d["status"] == "pending"


class TestPlanner:
    """测试 Planner — 需要 mock LLM"""

    def test_parse_valid_json(self):
        from agent.planner import Planner

        # 创建一个不会真实调 LLM 的 planner
        planner = Planner(llm=None)

        # 手动测试 _parse_response
        result = planner._parse_response(
            '[{"step": "gaussian", "action": "opt", "params": {}}]'
        )
        assert len(result) == 1
        assert result[0]["step"] == "gaussian"

    def test_parse_json_with_markdown_wrapper(self):
        from agent.planner import Planner
        planner = Planner(llm=None)

        raw = '```json\n[{"step": "gaussian", "action": "sp"}]\n```'
        result = planner._parse_response(raw)
        assert len(result) == 1
        assert result[0]["action"] == "sp"

    def test_parse_invalid_json(self):
        from agent.planner import Planner
        planner = Planner(llm=None)

        result = planner._parse_response("这不是 JSON")
        assert result == []
```

**`assert` 关键字：** Python 的断言，条件为 False 时抛 `AssertionError`。pytest 会捕获并报告哪些 assert 失败了。Go 里没有内置 assert，通常用 `if !ok { t.Fatal(...) }`。

**`TestAgentState` 和 `TestPlanner` 命名：** pytest 默认找 `test_*.py` 文件里 `Test*` 类里的 `test_*` 方法。这是约定，不是强制的。

### test_rag.py

```python
import pytest
from rag.chunker import Chunker


class TestChunker:
    def test_short_text(self):
        chunker = Chunker(chunk_size=512)
        chunks = chunker.chunk("短文本")
        assert len(chunks) == 1
        assert chunks[0]["text"] == "短文本"

    def test_long_text(self):
        chunker = Chunker(chunk_size=100, overlap=20)
        text = "A" * 250
        chunks = chunker.chunk(text)
        # 250 字符, chunk_size=100, overlap=20 → 第一个 0-100，第二个 80-180，第三个 160-250
        assert len(chunks) == 3

    def test_overlap(self):
        chunker = Chunker(chunk_size=100, overlap=20)
        text = "A" * 150
        chunks = chunker.chunk(text)
        # overlap=20, 第二个 chunk 的前 20 个字符应该和第一个 chunk 的后 20 个字符区域重叠
        assert chunks[1]["start"] == 80  # 100 - 20 = 80
```

### test_tools.py

```python
import pytest


class TestFakeTool:
    def test_mcp_client_fake_call(self):
        from agent.mcp_client import MCPClient
        mcp = MCPClient()
        result = mcp.call("gaussian", {"molecule": "test"})
        assert result["status"] == "success"
        assert result["tool"] == "gaussian"


class TestParser:
    def test_parse_conformers_empty(self):
        from tools.eqv2.parser import parse_conformers
        result = parse_conformers("")
        assert result == []

    def test_extract_orbital_energies(self):
        from tools.multiwfn.descriptor import extract_orbital_energies
        output = "HOMO energy: -0.28765 eV\nLUMO energy: -0.05000 eV"
        result = extract_orbital_energies(output)
        # 根据自己的 parser 逻辑调整断言
        assert isinstance(result, dict)
```

---

## 10.6 集成测试：端到端

新建 `tests/test_integration.py`：

```python
import pytest


class TestEndToEnd:
    """端到端集成测试 — 需要 LLM 可用"""

    @pytest.mark.integration
    def test_full_workflow_with_fake_tools(self):
        """用 fake 工具跑完整工作流"""
        from llm.client import LLMClient
        from agent.planner import Planner
        from agent.executor import Executor
        from agent.critic import Critic
        from agent.mcp_client import MCPClient
        from workflow.graph import build_workflow

        llm = LLMClient(model="qwen2.5:7b")
        planner = Planner(llm)
        mcp = MCPClient()
        executor = Executor(mcp)
        critic = Critic(llm)

        app = build_workflow(planner, executor, critic, retriever=None)

        result = app.invoke({
            "user_query": "优化苯结构",
            "current_step": 0,
            "retry_count": 0,
        })

        assert "plan" in result
        assert result.get("status") in ("done", "failed")
        # plan 应该非空
        assert len(result.get("plan", [])) > 0

    @pytest.mark.integration
    def test_with_rag(self):
        """带 RAG 的端到端测试"""
        from rag.chunker import Chunker
        from rag.embedder import Embedder
        from rag.vector_db import VectorDB
        from rag.retriever import Retriever
        from rag.ingestion import ingest_documents

        # 入库测试数据
        with open("/tmp/test_rag.txt", "w") as f:
            f.write("过渡态计算推荐 wB97XD。溶剂效应用 SMD 模型。")

        chunker = Chunker()
        embedder = Embedder()
        vector_db = VectorDB()
        retriever = Retriever(embedder, vector_db)
        ingest_documents(["/tmp/test_rag.txt"], chunker, embedder, vector_db)

        # 检索测试
        results = retriever.retrieve("过渡态用什么方法？")
        assert len(results) > 0
```

**`@pytest.mark.integration`**：给测试打标签。运行 `pytest -m integration` 只跑集成测试，`pytest -m "not integration"` 跳过集成测试（日常开发只跑快的单元测试）。

---

## 10.7 运行测试

```bash
cd /Users/Zhuanz/Documents/quantum-agent-platform

# 跑所有测试
python3 -m pytest tests/ -v

# 只跑单元测试（跳过需要 LLM 的）
python3 -m pytest tests/ -v -m "not integration"

# 只跑集成测试
python3 -m pytest tests/ -v -m integration

# 跑并输出覆盖率（需要装 pytest-cov）
python3 -m pytest tests/ --cov=. --cov-report=term-missing
```

---

## 10.8 构建评估数据集

在 `data/` 下新建 `eval_dataset.json`：

```json
[
  {
    "query": "优化苯的结构",
    "expected_steps": ["gaussian", "opt"],
    "expected_tools": ["gaussian"]
  },
  {
    "query": "计算乙醇的HOMO-LUMO能隙",
    "expected_steps": ["gaussian", "multiwfn"],
    "expected_tools": ["gaussian", "multiwfn"]
  },
  {
    "query": "搜索丁烷的最稳定构象",
    "expected_steps": ["eqv2"],
    "expected_tools": ["eqv2"]
  }
]
```

写一个专门跑评估的脚本 [scripts/run_eval.py](../scripts/run_eval.py)：

```python
"""运行评估 pipeline"""
import json
from llm.client import LLMClient
from agent.planner import Planner
from agent.executor import Executor
from agent.critic import Critic
from agent.mcp_client import MCPClient
from workflow.graph import build_workflow
from llmops.eval.agent_eval import evaluate_agent


def main():
    # 加载测试集
    with open("data/eval_dataset.json") as f:
        test_cases = json.load(f)

    # 构建 Agent
    llm = LLMClient(model="qwen2.5:7b")
    planner = Planner(llm)
    mcp = MCPClient()
    executor = Executor(mcp)
    critic = Critic(llm)
    app = build_workflow(planner, executor, critic, retriever=None)

    # 跑评估
    result = evaluate_agent(app, test_cases)

    print(f"总测试数: {result['total']}")
    print(f"通过: {result['passed']}")
    print(f"成功率: {result['success_rate']:.1%}")
    print(f"\n详细结果:")
    for d in result["details"]:
        status = "PASS" if d["passed"] else "FAIL"
        print(f"  [{status}] {d['query']} → {d['plan']}")


if __name__ == "__main__":
    main()
```

---

## 10.9 十个文件全貌

你的 `doc/` 目录下现在有完整的十节课：

```
doc/
├── lesson-01-fastapi.md           # 项目骨架 + HTTP 服务
├── lesson-02-llm-client.md        # LLM 调用封装
├── lesson-03-planner.md           # 任务拆解 Agent
├── lesson-04-executor-mcp-state.md # 调度 + 通信 + 状态机
├── lesson-05-critic-langgraph.md  # 结果检查 + DAG 闭环
├── lesson-06-real-tools.md        # subprocess 真实工具
├── lesson-07-rag.md               # 知识库检索系统
├── lesson-08-rag-agent.md         # RAG + Agent 融合
├── lesson-09-llmops.md            # 日志/缓存/追踪/成本
└── lesson-10-evaluation.md        # 评估指标 + 测试体系
```

---

## 10.10 平台做完后的样子

```
用户打开网页/终端
    ↓
POST /api/task/  {"task": "优化乙醇的过渡态，考虑溶剂效应"}
    ↓
LangGraph 工作流自启动：
    RAG → 检索课题组经验 → "用 wB97XD/def2-SVP + SMD"
    Plan → LLM 拆步骤 → [gaussian opt, gaussian sp, multiwfn]
    Exec → MCPClient 调工具 → subprocess 真实计算
    Critic → LLM 检查 → "SCF 收敛, HOMO=-0.287 eV, 正常"
    ↓
LLMOps 全程记录：日志、trace、成本
    ↓
返回结果：{"status": "done", "results": [...], "cost": "$0.03"}
```

---

## 10.11 本课检查清单

- [ ] 能写 pytest 测试，理解 `assert`、`Test*` 类、`test_*` 函数命名约定
- [ ] RAG 评估能输出 Recall@5 和 MRR
- [ ] Agent 评估能输出 Success Rate
- [ ] 系统评估能输出 Latency p95 和 Cost per task
- [ ] 能用 `pytest -m integration` 跑集成测试
- [ ] 能解释 p50/p95/p99 的区别
- [ ] 有一个 eval_dataset.json 测试集，至少 5 条测试用例

---

## 10.12 常见报错

| 报错 | 原因 | 解决 |
|------|------|------|
| `pytest: command not found` | 没装 | `pip3 install pytest` |
| `assert 0 == 1` 不显示详细信息 | pytest 不在调用链 | 确保用 `python3 -m pytest` 而不是直接 `pytest` |
| 集成测试跑不起来 | 需要 LLM 在线但没连上 | 先 `-m "not integration"` 跳过 |
| `KeyError: 'plan'` | workflow 返回的 state 里缺字段 | 检查 LangGraph node 是否正确写入 state |

---

## 课程完毕

十节课涵盖了从 FastAPI 启动到 LLMOps 全链路的每一个环节。每节课都是"讲一段原理 + 改一段代码 + 跑一个验证"的结构。你按照这个顺序一节节跟下来，平台就能一步步建起来。
