# Quantum Agent Platform

LLM 驱动的量子化学自主 Agent 平台。LangGraph 编排 RAG → 规划 → 执行 → 评审 四阶段工作流，集成量子化学工具链、SSE 流式反馈、多轮对话记忆与 Go 认证网关。

---

## 快速开始

```bash
git clone <repo-url> && cd quantum-agent-platform
cp .env.example .env          # 填入 LLM_API_KEY 和 EMBED_API_KEY
docker compose up -d          # 一键启动全部服务
# 浏览器打开 http://localhost:8000 → 注册 → 登录 → 使用
```

**前置条件**：Docker & Docker Compose、一个 LLM API Key（OpenAI 兼容接口）。

开发模式（只起基础设施，手动跑应用）：

```bash
docker compose up -d redis standalone mysql
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
cd auth && go run .
```

---

## 架构

```
浏览器 ──→ Go 认证网关 (:8080) ──→ FastAPI (:8000) ──→ LangGraph 工作流
            /api/auth/*  公开          /api/*  需 JWT
                                              │
            ┌─────────┬──────────┬──────────┼──────────┬──────────┐
          MySQL    Redis     Milvus      LLM     Embedding   量化工具
          用户表    会话记忆   向量检索                      Gaussian 等
```

**工作流四阶段**：

| 阶段 | 作用 |
|------|------|
| RAG | 用户问题向量化 → Milvus 相似搜索 → 返回知识片段 |
| Plan | LLM 拆解任务为 JSON 可执行步骤，SSE 实时推送思考 |
| Execute | 逐条调工具，失败自动重试，每步实时推送状态 |
| Critic | LLM 评审结果 → 通过则结束，否则回到 Execute（最多 3 轮） |

---

## 项目结构

```
quantum-agent-platform/
├── app/            # FastAPI 应用（路由、SSE、前端页面）
├── agent/          # Agent 核心（planner / executor / critic / mcp_client）
├── tools/          # 12 个内置工具（bash / gaussian / multiwfn / dipole …）
├── rag/            # RAG 检索（embedder / vector_db / retriever）
├── workflow/       # LangGraph DAG 编排
├── llm/            # LLM 调用封装（OpenAI 兼容，支持流式）
├── db/             # Redis 会话存储
├── memory/         # 长期记忆模块（MemoryManager + MemoryTool）
├── auth/           # Go 认证网关（登录/注册 + JWT + 反向代理）
├── config/         # 环境变量配置
├── docker-compose.yml
└── .env.example
```

---

## 内置工具

`bash` `read_file` `write_file` `list_dir` `delete_file` `python_repl` `grep_file`（内置 Gaussian 预设）`gaussian` `multiwfn` `eqv2` `homo_lumo` `dipole`

---

## API

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/` | Web 前端 |
| `POST` | `/api/workflow/stream` | Agent 工作流 — SSE 流式 |
| `POST` | `/api/workflow/run` | Agent 工作流 — 一次性返回 |
| `POST` | `/api/chat/stream` | 纯 LLM 对话 — SSE 流式 |
| `POST` | `/api/chat/` | 纯 LLM 对话 — 一次性返回 |
| `GET` | `/api/health/server` | 健康检查 |

SSE 事件：`thinking_chunk` `plan_done` `step_start` `step_done` `verdict_done` `retry` `done` `error`

---

## 配置

通过 `.env` 配置（见 `.env.example`）：

| 变量 | 说明 |
|------|------|
| `LLM_MODEL` / `LLM_BASE_URL` / `LLM_API_KEY` | LLM 模型与 API（**必填**） |
| `EMBED_MODEL` / `EMBED_BASE_URL` / `EMBED_API_KEY` | Embedding 模型与 API（RAG 需要） |
| `REDIS_HOST` / `MILVUS_HOST` | Docker 内自动改为服务名 |
| `MAX_RETRIES` / `MAX_STEPS` / `TOP_K` | 重试轮数 / 最大步骤数 / RAG 返回条数 |

---

## 添加工具

1. 写 `tools/<工具名>/runner.py`，定义纯函数（返回字符串）
2. 在 `tools/register_all.py` 注册：`registry.register_function(name, desc, schema, func)`
3. 需要时在 `agent/prompts/planner_prompt.txt` 补充用法说明

```python
def run_your_tool(required_param: str, optional_param: bool = False) -> str:
    """一句话描述"""
    return "格式化结果字符串"
```

---

## 优雅降级

依赖缺失不会崩溃：Redis 没起 → 无多轮记忆；Milvus 没起 → 无 RAG；都没开 → LLM 对话依然正常。

---

## 技术栈

FastAPI + SSE · LangGraph · Milvus · Redis · Docker Compose · Go 认证网关 · 原生前端

---

## License

MIT
