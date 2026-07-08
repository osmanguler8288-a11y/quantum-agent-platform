# Quantum Agent Platform — 十节课程大纲

## 项目总览

构建一个面向量子化学计算的 LLM + RAG + LLMOps 科研计算平台，实现自然语言驱动量子化学工具自动执行。

核心能力：Planner（拆任务）→ Executor（调工具）→ Critic（查结果）→ 生成报告

---

## 涉及技术栈总表

| 类别 | 技术 | 学什么 |
|------|------|--------|
| 后端框架 | FastAPI + Uvicorn | 路由、请求/响应模型、服务启动 |
| Agent 框架 | LangGraph | DAG 工作流、节点定义、条件跳转 |
| LLM 调用 | OpenAI SDK / Ollama | prompt 工程、多模型路由 |
| 向量数据库 | Milvus / PyMilvus | 向量存储、相似检索 |
| 缓存 | Redis | 结果缓存、任务状态存储 |
| 嵌入模型 | bge / text-embedding | chunk 转向量、语义检索 |
| 工具执行 | subprocess | 调命令行工具、进程管理 |
| 可观测性 | 自建 logger/tracer | 全链路日志、执行追踪、成本统计 |
| 数据格式 | YAML + Pydantic | 配置管理、数据校验 |
| 测试 | pytest | 单元测试、集成测试 |

---

## 第一课：项目骨架搭建 + FastAPI 跑起来

**目标：** 理解 Python 项目结构，让第一个 HTTP 服务跑起来

**内容：**
- Python 项目标准目录结构（app/、tools/、config/ 你已经有雏形）
- FastAPI 是什么：声明式路由、自动生成 Swagger 文档
- uvicorn 是什么：ASGI 服务器，把 FastAPI 变成真正的网络服务
- Pydantic 请求/响应模型：输入校验、输出格式化

**技术栈：** FastAPI、Uvicorn、Pydantic

**第一节验收：**
```bash
curl http://localhost:8000/api/chat/ -X POST -d '{"message":"hello"}'
# 返回: {"message": "chat endpoint"}
```

---

## 第二课：LLM Client 封装 + Prompt Engine

**目标：** 封装 LLM 调用，让程序能跟大模型对话

**内容：**
- OpenAI SDK 统一接口（兼容 Qwen/Ollama）
- `llm/client.py`：封装 `generate()` 和 `chat()` 方法
- `llm/prompt_engine.py`：模板注册 + 变量渲染（f-string 和 Jinja2 思路）
- `llm/router.py`：根据任务类型路由到不同模型（规划用大模型，检查用小模型）
- 环境变量 / YAML 配置管理

**技术栈：** OpenAI SDK、Ollama、YAML、环境变量

**第二节验收：**
```python
client = LLMClient(model="qwen2.5:72b")
response = client.generate("解释什么是HOMO能级")
# 终端能看到 LLM 返回的真实文本
```

---

## 第三课：Planner — 让 LLM 拆任务

**目标：** 实现第一个 Agent 能力：自然语言 → 可执行计划

**内容：**
- Prompt 工程实战：怎么写 Planner 的 system prompt
- 让 LLM 输出结构化数据（JSON 格式约束）
- `agent/planner.py`：加载 prompt、调 LLM、解析输出
- `_parse_plan()` 解析：从 LLM 文本提取步骤列表
- few-shot 示例：在 prompt 里给示例，让输出更稳定

**技术栈：** Prompt Engineering、JSON Schema、Python dict/list 操作

**第三节验收：**
```python
plan = planner.plan({"task": "优化乙醇结构并计算HOMO"})
# plan = [
#   {"step": "gaussian", "action": "opt", "params": {...}},
#   {"step": "gaussian", "action": "sp", "params": {...}},
#   {"step": "multiwfn", "action": "homo", "params": {...}},
# ]
```

---

## 第四课：Executor + MCPClient — 调度与通信

**目标：** 遍历 plan，调 MCPClient 把任务派发出去

**内容：**
- `agent/executor.py`：遍历 plan，按 step 调度
- `agent/mcp_client.py`：统一通信接口，屏蔽工具差异
- MCP 协议概念：Client ↔ Server ↔ Tool 的通信模型
- 错误处理：工具调用失败怎么办？重试几次？
- `agent/state.py`：状态机（pending → executing → done/failed）

**技术栈：** 状态机模式、异常处理（try/except）、MCP 协议

**第四节验收：**
```python
executor.execute(plan, input_data)
# [execute] step=gaussian, result=fake_result_from_gaussian
# [execute] step=multiwfn, result=fake_result_from_multiwfn
```

---

## 第五课：Critic — 结果检查 + LangGraph 工作流串通

**目标：** 实现自纠错闭环，Planner → Executor → Critic 形成 DAG

**内容：**
- `agent/critic.py`：让 LLM 检查计算结果是否合理
- 判断逻辑：物理常识检查（能量数量级对不对？收敛了吗？）
- `workflow/graph.py`：LangGraph 把三个 Agent 串成 DAG
- 条件跳转：Critic 说 pass → 结束；fail → 跳回 Executor 重试
- State 在节点间流转

**技术栈：** LangGraph、DAG 工作流、条件路由

**第五节验收：**
```
用户输入 → PlanNode → ExecNode → CritiqueNode
                ↑                    │
                └── retry ──────────┘  (fail)
                      ↓
                    END  (pass)
```
整个闭环跑通，用 fake 工具返回结果，Critic 能判断 pass/fail。

---

## 第六课：真实工具接入 — subprocess 调量子化学程序

**目标：** 替换 fake 工具，真实调起 Gaussian/EqV2/Multiwfn

**内容：**
- `subprocess.run()`：Python 调命令行程序
- `tools/eqv2/runner.py`：调 EqV2，传输入文件，拿输出
- `tools/gaussian/runner.py`：调 g16，监控任务完成
- `tools/multiwfn/runner.py`：用管道传命令给 Multiwfn
- 进程管理：超时杀掉、错误捕获、输出解析

**技术栈：** subprocess、进程管理、量子化学工具命令行操作

**第六节验收：**
```python
result = run_gaussian("ethanol.gjf", "ethanol.log")
# result 是 g16 的真实输出，不是 fake
```

---

## 第七课：RAG 系统 — 知识入库与检索

**目标：** 让 Agent 在做事之前先查"课题组经验库"

**内容：**
- `rag/chunker.py`：长文档切片（滑动窗口，重叠 50 字）
- `rag/embedder.py`：调 bge 模型把文本转成向量（1536 维数组）
- `rag/vector_db.py`：Milvus 存向量 + 元数据
- `rag/retriever.py`：输入查询 → embedding → Milvus.search() → 返回相关文档
- `rag/ingestion.py`：批量文档入库脚本

**技术栈：** Embedding 模型（bge）、Milvus、向量检索

**第七节验收：**
```python
docs = retriever.retrieve("过渡态计算用什么泛函？", top_k=3)
# 返回课题组经验库里的相关文献片段
```

---

## 第八课：RAG + Agent 融合

**目标：** 知识检索嵌入 Agent 工作流，Plan 之前先查资料

**内容：**
- RAG Node：在 Planner 之前增加检索步骤
- 检索结果拼进 Planner 的 prompt（"根据以下参考资料拆任务：...")
- `workflow/nodes/rag_node.py`：实现查 → 拼 → 传
- 评估检索质量：Recall@K、MRR

**技术栈：** LangGraph 节点扩展、Prompt 拼接、信息检索评估

**第八节验收：**
```
用户输入 → RAGNode（查资料）→ PlanNode（带资料拆任务）→ ExecNode → CritiqueNode
```
Planner 拆出来的步骤包含了检索到的经验（如用了特定基组）。

---

## 第九课：LLMOps — 日志、缓存、追踪、成本

**目标：** 让平台可观测、可调试、省钱

**内容：**
- `llmops/logger.py`：全链路日志（每次 LLM 调用 + 工具执行）
- `llmops/cache.py`：Redis 缓存（同样输入不重复算）
- `llmops/tracer.py`：执行追踪（每一步耗时、输入输出）
- `llmops/cost.py`：统计 token 消耗 / GPU 时间
- `llmops/state_store.py`：持久化任务状态

**技术栈：** Redis、结构化日志、性能统计

**第九节验收：**
```python
tracer.start("planner")
# ... planner 执行 ...
tracer.end(trace_id)
print(tracer.summary())
# [{"name": "planner", "duration_ms": 234, "tokens": 512}, ...]
```

---

## 第十课：Evaluation + 全链路集成测试

**目标：** 量化系统好坏，写出可复现的评估指标

**内容：**
- `llmops/eval/agent_eval.py`：任务成功率（几次跑对的？）
- `llmops/eval/rag_eval.py`：检索 Recall@K / MRR
- `llmops/eval/system_eval.py`：延迟 p95 / 单次成本
- 集成测试：从 HTTP 请求到工具执行，端到端跑通
- `tests/` 下写 pytest 用例

**技术栈：** pytest、评估指标体系、端到端测试

**第十节验收：**
- 10 个测试任务，统计成功率 > 80%
- 延迟 p95 < 5 分钟（含计算时间）
- 缓存命中率 > 30%

---

## 学习路线图

```
第一课 ──→ 第二课 ──→ 第三课 ──→ 第四课 ──→ 第五课
基础搭建    LLM通信    任务拆解    调度通信    闭环串联
   │          │          │          │          │
   └──────────┴──────────┴──────────┴──────────┘
                     第一阶段完成
                     Agent 闭环跑通
                         │
           ┌─────────────┴─────────────┐
           │                           │
        第六课                       第七课
       真实工具                     RAG入库
           │                           │
           └─────────────┬─────────────┘
                         │
                       第八课
                    RAG + Agent 融合
                         │
                   第九课 LLMOps
                         │
                   第十课 Evaluation
                    全链路完成
```

## 每节课用时建议

| 课次 | 主题 | 建议时间 |
|------|------|---------|
| 第一课 | 项目骨架 + FastAPI | 1-2 天 |
| 第二课 | LLM Client 封装 | 1-2 天 |
| 第三课 | Planner 任务拆解 | 2-3 天 |
| 第四课 | Executor + MCPClient | 2-3 天 |
| 第五课 | Critic + LangGraph 闭环 | 3-4 天 |
| 第六课 | 真实工具接入 | 1-2 天 |
| 第七课 | RAG 系统 | 3-4 天 |
| 第八课 | RAG + Agent 融合 | 2-3 天 |
| 第九课 | LLMOps | 2-3 天 |
| 第十课 | Evaluation + 测试 | 2-3 天 |
