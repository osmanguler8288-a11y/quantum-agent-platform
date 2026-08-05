# Quantum Agent Platform

LLM 驱动的量子化学自主 Agent 平台。LangGraph 编排 **记忆检索 → RAG → 规划 → 执行 → 评审** 五阶段工作流，集成量子化学工具链、SSE 流式反馈、双层记忆系统（Redis 短期对话 + Milvus 长期记忆）与 Go 认证网关。

---

## 快速开始

```bash
git clone <repo-url> && cd quantum-agent-platform
cp .env.example .env          # 填入 LLM_API_KEY 和 EMBED_API_KEY
docker compose up -d          # 一键启动全部服务
# 浏览器打开 http://localhost:8080 → 注册 → 登录 → 使用
# 注意：必须访问 :8080（Go 网关），:8000 是内部 FastAPI，无认证路由
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
            JWT 注入 X-User-ID                │
                                              ↓
            ┌─────────┬──────────┬──────────┬──────────┬──────────┐
          MySQL    Redis      Milvus       LLM      Embedding   量化工具
          用户表   短期对话    长期记忆+RAG                      Gaussian 等
```

**工作流五阶段**：

| 阶段 | 作用 |
|------|------|
| Memory | 用户问题 → 检索相关长期记忆（按 user_id 隔离）→ 注入 Planner 上下文 |
| RAG | 用户问题向量化 → Milvus 相似搜索 → 返回知识片段 |
| Plan | LLM 拆解任务为 JSON 可执行步骤，SSE 实时推送思考 |
| Execute | 逐条调工具，失败自动重试，每步实时推送状态 |
| Critic | LLM 评审结果 → 通过则结束，否则回到 Execute（最多 3 轮） |

---

## 双层记忆系统

| 层级 | 存储 | 隔离 | TTL | 用途 |
|------|------|------|-----|------|
| **短期对话** | Redis | session_id | 1 小时 | 单会话多轮上下文，注入 Planner prompt |
| **长期记忆** | Milvus | user_id | 永久（除非被遗忘） | 跨会话用户偏好、知识积累 |

### 长期记忆的四种类型

| 类型 | 含义 | 写入时机 |
|------|------|---------|
| `working` | 短期工作记忆 | Agent 主动调 `memory_add` 工具 |
| `episodic` | 情景记忆（具体事件） | **任务结束自动写入**，LLM 自评 importance |
| `semantic` | 语义知识（抽象共性） | **自动整合**：episodic 中 importance ≥ 0.7 被 LLM 抽取共性 |
| `perceptual` | 感知记忆（多模态预留） | Agent 主动调，支持文件路径自动推断模态 |

### 自动闭环

```
对话发生
   ↓
[自动] LLM 自评 importance（0.0~1.0）→ 写入 episodic
   ↓
[自动] 每存 5 条触发 consolidate
   ↓
[自动] importance ≥ 0.7 → LLM 抽取共性 → 写入 semantic
   ↓
[自动] 后台每天扫一次 → 清理 importance < 0.2 或 > 30 天的老旧记忆
```

### 高级特性

- **重要性自评**：写入前调 LLM 按 1.0/0.7/0.4/0.2 四档标准评分
- **自动整合**：高重要性 episodic → LLM 抽取共性 → 升级为 semantic 知识
- **遗忘机制**：低重要性或老旧记忆自动清理（importance_based / age_based / combined 三种策略）
- **时效衰减**：检索时按半衰期 7 天做指数衰减，新记忆权重更高
- **多用户隔离**：每个用户独立 MemoryTool 实例，检索/写入均按 user_id 过滤

### 记忆管理 API

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/workflow/history` | 查看当前用户的所有长期记忆 |
| `POST` | `/api/workflow/memory/consolidate` | 手动触发整合（episodic → semantic） |
| `POST` | `/api/workflow/memory/forget` | 手动触发遗忘（清理低重要性记忆） |

### 记忆相关工具（Agent 可调用）

`memory_add` `memory_search` `memory_consolidate` `memory_forget` `memory_history`

---

## 项目结构

```
quantum-agent-platform/
├── app/            # FastAPI 应用（路由、SSE、前端页面）
├── agent/          # Agent 核心（planner / executor / critic / mcp_client）
├── tools/          # 17 个内置工具（12 量化 + 5 记忆管理）
├── rag/            # RAG 检索（embedder / vector_db / retriever）
├── workflow/       # LangGraph DAG 编排（memory / rag / plan / exec / critic）
├── llm/            # LLM 调用封装（OpenAI 兼容，支持流式）
├── db/             # Redis 会话存储
├── memory/         # 长期记忆模块（MemoryManager / MilvusStore / 4 种记忆类型 / Scheduler）
├── auth/           # Go 认证网关（登录/注册 + JWT + 反向代理）
├── config/         # 环境变量配置
├── docker-compose.yml
└── .env.example
```

---

## 内置工具

**量化与系统**：`bash` `read_file` `write_file` `list_dir` `delete_file` `python_repl` `grep_file`（内置 Gaussian 预设）`gaussian` `multiwfn` `eqv2` `homo_lumo` `dipole`

**记忆管理**：`memory_add` `memory_search` `memory_consolidate` `memory_forget` `memory_history`

---

## API

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/` | Web 前端 |
| `POST` | `/api/workflow/stream` | Agent 工作流 — SSE 流式 |
| `POST` | `/api/workflow/run` | Agent 工作流 — 一次性返回 |
| `POST` | `/api/workflow/memory/consolidate` | 手动触发记忆整合 |
| `POST` | `/api/workflow/memory/forget` | 手动触发遗忘机制 |
| `GET` | `/api/workflow/history` | 查看当前用户长期记忆 |
| `POST` | `/api/chat/stream` | 纯 LLM 对话 — SSE 流式 |
| `POST` | `/api/chat/` | 纯 LLM 对话 — 一次性返回 |
| `GET` | `/api/health/server` | 健康检查 |

SSE 事件：`memory_done` `rag_done` `thinking_chunk` `plan_done` `step_start` `step_done` `verdict_done` `retry` `done` `error`

---

## 配置

通过 `.env` 配置（见 `.env.example`）：

| 变量 | 说明 |
|------|------|
| `LLM_MODEL` / `LLM_BASE_URL` / `LLM_API_KEY` | LLM 模型与 API（**必填**） |
| `EMBED_MODEL` / `EMBED_BASE_URL` / `EMBED_API_KEY` | Embedding 模型与 API（RAG 与记忆检索需要） |
| `MYSQL_DSN` | Go 认证服务连接 MySQL（Docker 部署不用改） |
| `JWT_SECRET` | JWT 签名密钥（生产环境请换成随机长字符串） |
| `BACKEND_URL` | Go 网关转发目标（Docker 内自动用 `http://app:8000`） |
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

依赖缺失不会崩溃：Redis 没起 → 无多轮记忆；Milvus 没起 → 无 RAG 与长期记忆；都没开 → LLM 对话依然正常。

---

## 技术栈

FastAPI + SSE · LangGraph · Milvus · Redis · Docker Compose · Go 认证网关 · 原生前端 · DeepSeek LLM

---

## License

MIT
