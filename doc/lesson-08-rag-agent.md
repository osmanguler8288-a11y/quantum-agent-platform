# 第八课：RAG + Agent 融合

## 本课目标

- 把 RAG 检索嵌入 LangGraph 工作流
- Planner 先查资料再拆任务
- 理解 Prompt 拼接模式：system + context + user
- 评估检索质量（Recall@K、MRR）

## 前置要求

- 第五课完成（LangGraph 闭环）
- 第七课完成（RAG 入库和检索）

---

## 8.1 融合架构

之前的工作流：`Plan → Exec → Critic → END`

现在加一个 RAG 节点：`RAG → Plan → Exec → Critic → END`

```
用户输入
    ↓
RAG Node（检索知识库）
    ↓  返回相关经验/文献
Plan Node（带着知识拆任务）
    ↓  产出更靠谱的 plan
Exec → Critic → END
```

**效果对比：**

```
没有 RAG：
  用户："算过渡态"
  Planner："用 B3LYP/6-31G(d)"（LLM 瞎猜的）

有 RAG：
  用户："算过渡态"
  RAG 检索到："课题组经验：有机过渡态用 wB97XD/def2-SVP 精度更好"
  Planner："根据课题组经验，用 wB97XD/def2-SVP"（有依据的）
```

---

## 8.2 改造 RAG Node

[workflow/nodes/rag_node.py](../workflow/nodes/rag_node.py) 当前是骨架。填入逻辑：

```python
def make_rag_node(retriever):
    """创建 RAG 节点——查资料并拼进 state"""
    def rag_node(state: dict) -> dict:
        query = state.get("user_query", "")

        # 1. 检索
        docs = retriever.retrieve(query, top_k=3)

        # 2. 拼成一段可读的文本
        context_parts = []
        for i, doc in enumerate(docs, start=1):
            context_parts.append(
                f"[参考资料{i}] (相似度:{doc['similarity']:.2f})\n{doc['text']}"
            )
        context = "\n\n".join(context_parts) if context_parts else "（未找到相关资料）"

        # 3. 写入 state，供 Plan Node 使用
        state["rag_context"] = context
        state["rag_docs"] = docs
        print(f"[rag] 检索到 {len(docs)} 条资料")
        return state

    return rag_node
```

`"\n\n".join(context_parts)`：以两个换行符为分隔符，把字符串列表拼成一个大字符串。Go：`strings.Join(contextParts, "\n\n")`。

---

## 8.3 改造 Plan Node：把 RAG 结果拼进 prompt

Planner 的 prompt 里新增一个 `{context}` 占位符：

在 `agent/prompts/planner_prompt.txt` 最前面加：

```
## 参考资料（来自课题组知识库）
{context}

## 用户任务
{task}

...
```

然后在 [agent/planner.py](../agent/planner.py) 里填进去：

```python
class Planner:
    def __init__(self, llm: LLMClient):
        self.llm = llm

    def plan(self, task: str, context: str = "") -> list[dict]:
        prompt = self._load_prompt()

        # 先填 context（即使为空也不会崩溃）
        filled = prompt.replace("{context}", context)
        filled = filled.replace("{task}", task)

        raw = self.llm.generate(filled)
        return self._parse_response(raw)
```

**改动很小——传一个 `context` 参数进去填充模板即可。** 这就是 RAG 和 Agent 融合的本质：不是重写 Planner，而是在调 Planner 之前多塞一段背景信息。

---

## 8.4 改造 LangGraph 工作流

更新 [workflow/graph.py](../workflow/graph.py) 里的 `build_workflow`，加入 RAG 节点：

```python
from workflow.nodes.rag_node import make_rag_node


def build_workflow(planner, executor, critic, retriever):
    """构建带 RAG 的 LangGraph 工作流"""

    # 用工厂函数创建节点
    rag_fn = make_rag_node(retriever)

    def plan_node(state: dict) -> dict:
        state["status"] = "planning"
        query = state.get("user_query", "")
        context = state.get("rag_context", "")
        plan = planner.plan(query, context=context)  # ← 把 context 传进去
        state["plan"] = plan
        print(f"[workflow] plan: {len(plan)} steps")
        return state

    def exec_node(state: dict) -> dict:
        state["status"] = "executing"
        plan = state.get("plan", [])
        idx = state.get("current_step", 0)
        if idx < len(plan):
            step = plan[idx]
            result = executor.mcp.call(
                step.get("step", "unknown"),
                step.get("params", {}),
            )
            state.setdefault("results", []).append({
                "step_idx": idx, "step": step, "result": result,
            })
            state["last_result"] = result
        return state

    def critic_node(state: dict) -> dict:
        state["status"] = "reviewing"
        idx = state.get("current_step", 0)
        plan = state.get("plan", [])
        if idx < len(plan):
            review = critic.review(plan[idx], state.get("last_result", {}),
                                   state.get("user_query", ""))
            state["critic_passed"] = review.get("passed", True)
        return state

    def route_after_critic(state: dict) -> str:
        if not state.get("critic_passed", True):
            state["retry_count"] = state.get("retry_count", 0) + 1
            if state["retry_count"] >= 3:
                state["status"] = "failed"
                return "done"
            return "retry"

        state["current_step"] = state.get("current_step", 0) + 1
        if state["current_step"] >= len(state.get("plan", [])):
            state["status"] = "done"
            return "done"
        return "next"

    # --- 构建图 ---
    from langgraph.graph import StateGraph, END

    graph = StateGraph(dict)

    graph.add_node("rag", rag_fn)
    graph.add_node("plan", plan_node)
    graph.add_node("exec", exec_node)
    graph.add_node("critic", critic_node)

    graph.set_entry_point("rag")       # ← 入口改为 RAG
    graph.add_edge("rag", "plan")      # rag → plan
    graph.add_edge("plan", "exec")     # plan → exec
    graph.add_edge("exec", "critic")   # exec → critic

    graph.add_conditional_edges(
        "critic", route_after_critic,
        {"next": "exec", "retry": "exec", "done": END},
    )

    return graph.compile()
```

**改动总结：**

1. 入口从 `"plan"` 改为 `"rag"` — 请求先查资料再规划
2. 新增 `rag_fn` 节点 — 检索知识库，结果写进 `state["rag_context"]`
3. `plan_node` 调用 `planner.plan(query, context=...)` — 把检索结果传给 Planner

---

## 8.5 端到端测试：带 RAG 的 Agent

```python
"""测试 RAG + Agent 完整链路"""
from llm.client import LLMClient
from agent.planner import Planner
from agent.executor import Executor
from agent.critic import Critic
from agent.mcp_client import MCPClient
from rag.chunker import Chunker
from rag.embedder import Embedder
from rag.vector_db import VectorDB
from rag.retriever import Retriever
from rag.ingestion import ingest_documents
from workflow.graph import build_workflow

# 1. 准备 RAG 知识库
knowledge = """
课题组经验：有机小分子过渡态计算推荐使用 wB97XD/def2-SVP。
溶剂效应：极性溶剂使用 SMD 模型。
构象搜索：柔性分子至少生成 50 个初始构象。
HOMO-LUMO 能隙 < 0.3 eV 的体系建议使用多参考方法 CASPT2。
"""
with open("/tmp/group_knowledge.txt", "w") as f:
    f.write(knowledge)

chunker = Chunker(chunk_size=200, overlap=30)
embedder = Embedder()
vector_db = VectorDB()
retriever = Retriever(embedder, vector_db)
ingest_documents(["/tmp/group_knowledge.txt"], chunker, embedder, vector_db)

# 2. 创建 Agent 组件
llm = LLMClient(model="qwen2.5:7b")
planner = Planner(llm)
mcp = MCPClient()
executor = Executor(mcp)
critic = Critic(llm)

# 3. 构建工作流（带 RAG）
app = build_workflow(planner, executor, critic, retriever)

# 4. 跑任务 — 注意 RAG 是否能改变 Planner 的行为
result = app.invoke({
    "user_query": "计算乙醇过渡态，考虑溶剂效应",
    "current_step": 0,
    "retry_count": 0,
})

print(f"\n状态: {result.get('status')}")
print(f"Plan: {result.get('plan')}")
print(f"RAG 资料: {result.get('rag_context', '')[:200]}...")
print(f"执行了 {len(result.get('results', []))} 步")
```

**关键验证点：** Planner 输出里是否包含了 RAG 资料的内容？比如是否指定了 `wB97XD` 或 `SMD` 而不是默认的 `B3LYP`。

---

## 8.6 评估检索质量

光能跑不行，还要量化检索好不好。打开 [llmops/eval/rag_eval.py](../llmops/eval/rag_eval.py)：

```python
def compute_recall_at_k(retrieved_doc_ids: list[str],
                         relevant_doc_ids: list[str], k: int = 5) -> float:
    """Recall@K：检索到的前K条里，包含了多少相关文档。
    比如共有 5 篇相关文档，前 3 条检索结果包含了 2 篇 → Recall@3 = 2/5 = 0.4
    """
    if not relevant_doc_ids:
        return 0.0
    retrieved_k = set(retrieved_doc_ids[:k])
    relevant = set(relevant_doc_ids)
    return len(retrieved_k & relevant) / len(relevant)


def compute_mrr(retrieved_doc_ids: list[str],
                relevant_doc_ids: list[str]) -> float:
    """MRR（Mean Reciprocal Rank）：第一个相关文档排在第几位。
    排第 1 → 1/1 = 1.0，排第 5 → 1/5 = 0.2
    """
    for i, doc_id in enumerate(retrieved_doc_ids, start=1):
        if doc_id in relevant_doc_ids:
            return 1.0 / i
    return 0.0


# 测试
retrieved = ["doc3", "doc1", "doc5", "doc2"]
relevant = ["doc2", "doc3"]
print(f"Recall@3: {compute_recall_at_k(retrieved, relevant, 3):.2f}")  # 2/2 = 1.0
print(f"MRR: {compute_mrr(retrieved, relevant):.2f}")                  # 1/3 = 0.33
```

**这两个指标的关系：**

- **MRR**：用户在乎"第一个对的在不在前三"。用来优化用户体验。
- **Recall@K**：用户在乎"所有相关的都找到了吗"。用来保证不遗漏。

科研场景下 Recall 更重要——你不能漏掉关键文献。但我们更偏向于 MRR：第一条返回结果对了，体验才好。

---

## 8.7 改造后的完整工作流

```
                       ┌─────────┐
用户输入 ──────────────→│   RAG   │ 查知识库
                       └────┬────┘
                            │ state["rag_context"]
                       ┌────▼────┐
                       │  plan   │ 带资料拆任务
                       └────┬────┘
                            │
                       ┌────▼────┐
                 ┌─────│  exec   │ 执行
                 │     └────┬────┘
                 │          │
                 │     ┌────▼────┐
                 │     │ critic  │ 检查
                 │     └────┬────┘
                 │          │
                 └──────────┘ (retry)
                            │
                         ┌──▼──┐
                         │ END │
                         └─────┘
```

---

## 8.8 本课检查清单

- [ ] RAG 节点在工作流里正确执行，state 中有 `rag_context`
- [ ] Planner 调用时传入了 `context` 参数
- [ ] 能观察 Planner 输出是否受 RAG 资料影响
- [ ] 能解释 `"\n\n".join(list)` 和 Go 的 `strings.Join` 异同
- [ ] 能手动算一遍 Recall@K 和 MRR
- [ ] 端到端跑通了 RAG → Plan → Exec → Critic 完整链路

---

## 8.9 常见报错

| 报错 | 原因 | 解决 |
|------|------|------|
| RAG context 为空 | retriever 没初始化好或没入库 | 先单独测 retriever.retrieve() |
| Planner 没用到 RAG | prompt 模板里没 `{context}` | 检查 planner_prompt.txt 里是否有这个占位符 |
| `KeyError: 'rag_context'` | RAG 节点没加到图里或执行顺序不对 | 确认 `set_entry_point("rag")` |
| 检索结果不相关 | embedding 质量差或 chunk 切得不好 | 尝试不同的 chunk_size 或 embedding 模型 |

---

现在前三节（框架基础）和 4-8 节（Agent 闭环 + 工具 + RAG）都有了。后续第九课（LLMOps）和第十课（Evaluation + 测试）如果需要我也继续写。
