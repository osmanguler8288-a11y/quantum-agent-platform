# Quantum Agent Platform

LLM 驱动的量子化学自主 Agent 平台。LangGraph 编排 **记忆检索 → RAG → 规划 → 执行 → 评审** 五阶段工作流，集成量子化学工具链、SSE 流式反馈、双层记忆系统（Redis 短期对话 + Milvus 长期记忆）与 Go 认证网关。

**前后端分离**：`frontend/`（Vue 3 + Vite）负责交互界面，`backend/`（FastAPI + LangGraph）负责 Agent 编排与工具执行。

---

## 快速开始

### 一键启动（Docker Compose）

```bash
git clone <repo-url> && cd quantum-agent-platform
cd backend
cp .env.example .env          # 填入 LLM_API_KEY 和 EMBED_API_KEY
docker compose up -d          # 启动 mysql / redis / app / auth / milvus 等全部服务
# 浏览器打开 http://localhost:8080 → 注册 → 登录 → 使用
# 注意：必须访问 :8080（Go 网关），:8000 是内部 FastAPI，无认证路由
```

**前置条件**：Docker & Docker Compose、一个 LLM API Key（OpenAI 兼容接口）。

### 本地开发（前后端分离）

```bash
# 后端（backend/ 目录下运行）
cd backend
cp .env.example .env
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8001

# 前端（frontend/ 目录下运行）
cd ../frontend
npm install
npm run dev                   # Vite 开发服务器，默认 http://localhost:5173
```

开发模式下前端走 mock 数据（`VITE_USE_MOCK=true`）；联调真实后端时设 `VITE_USE_MOCK=false` 并指向后端地址。

---

## 架构

```
浏览器 ──→ Vue 3 前端 (:8000 静态 / :5173 dev) ──→ Go 认证网关 (:8080) ──→ FastAPI (:8001)
                     /api/auth/*  公开                          /api/*  需 JWT
                     JWT 注入 X-User-ID                              │
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
├── backend/               # 后端（FastAPI + LangGraph + Agent 核心）
│   ├── app/               # FastAPI 应用（main / routes / schemas / utils）
│   │   └── utils/logger.py  # loguru 统一日志（request_id / trace_id / 脱敏）
│   ├── agent/             # Agent 核心（planner / executor / critic / mcp_client）
│   ├── tools/             # 内置工具（量化 + 记忆管理）
│   ├── rag/               # RAG 检索（embedder / vector_db / retriever）
│   ├── workflow/          # LangGraph DAG 编排（memory / rag / plan / exec / critic）
│   ├── llm/               # LLM 调用封装（OpenAI 兼容，支持流式）
│   ├── llmops/            # LLM Ops（评估 / 监控）
│   ├── db/                # Redis 会话存储
│   ├── memory/            # 长期记忆模块（MemoryManager / MilvusStore / Scheduler）
│   ├── auth/              # Go 认证网关（登录/注册 + JWT + 反向代理）
│   ├── config/            # 环境变量配置
│   ├── requirements.txt   # Python 依赖
│   └── docker-compose.yml # 基础设施编排（mysql / redis / app / auth / milvus）
├── frontend/              # 前端（Vue 3 + Vite + Pinia + Vue Router）
│   ├── src/               # 源码（views / components / stores / api / router）
│   ├── serve.py           # 生产静态服务（http.server SPA，端口 8000）
│   ├── package.json
│   └── vite.config.ts
├── doc/                   # 项目文档与教程（lesson-01 ~ lesson-10）
├── deploy.sh              # 部署脚本（前后端分离，SSH 推送到服务器）
└── README.md
```

---

## 内置工具

**量化与系统**：`bash` `read_file` `write_file` `list_dir` `delete_file` `python_repl` `grep_file`（内置 Gaussian 预设）`gaussian` `multiwfn` `eqv2` `homo_lumo` `dipole`

**记忆管理**：`memory_add` `memory_search` `memory_consolidate` `memory_forget` `memory_history`

---

## API

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/chat/` | 纯 LLM 对话 — 一次性返回 |
| `POST` | `/api/chat/stream` | 纯 LLM 对话 — SSE 流式 |
| `POST` | `/api/task/` | 单任务执行 |
| `POST` | `/api/workflow/run` | Agent 工作流 — 一次性返回 |
| `POST` | `/api/workflow/stream` | Agent 工作流 — SSE 流式 |
| `GET` | `/api/workflow/history` | 查看当前用户长期记忆 |
| `POST` | `/api/workflow/memory/consolidate` | 手动触发记忆整合 |
| `POST` | `/api/workflow/memory/forget` | 手动触发遗忘机制 |
| `GET` | `/api/health/server` | 健康检查 |
| `GET` | `/api/status/ping` | 状态探测 |

SSE 事件：`memory_done` `rag_done` `thinking_chunk` `plan_done` `step_start` `step_done` `verdict_done` `retry` `done` `error`

---

## 配置

通过 `backend/.env` 配置（见 `backend/.env.example`）：

| 变量 | 说明 |
|------|------|
| `LLM_MODEL` / `LLM_BASE_URL` / `LLM_API_KEY` | LLM 模型与 API（**必填**） |
| `EMBED_MODEL` / `EMBED_BASE_URL` / `EMBED_API_KEY` | Embedding 模型与 API（RAG 与记忆检索需要） |
| `MYSQL_DSN` | Go 认证服务连接 MySQL（Docker 部署不用改） |
| `JWT_SECRET` | JWT 签名密钥（生产环境请换成随机长字符串） |
| `SKIP_AUTH` | 本地开发跳过 SSO 认证（`true` 使用固定用户 `local_dev`；生产务必 `false`） |
| `BACKEND_URL` | Go 网关转发目标（Docker 内自动用 `http://app:8000`） |
| `REDIS_HOST` / `REDIS_PORT` | Redis 连接（Docker 内自动改为服务名） |
| `MILVUS_HOST` / `MILVUS_PORT` | Milvus 连接（Docker 内自动改为服务名） |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` / `TOP_K` | RAG 分块与返回条数 |
| `MAX_RETRIES` / `MAX_STEPS` | 重试轮数 / 最大步骤数 |

---

## 部署

生产环境部署**必须通过 `deploy.sh`**，脚本内置根目录校验、SSH 密码注入、远端路径护栏与健康检查。

```bash
cd <项目根目录>
DEPLOY_PASSWORD='<服务器密码>' ./deploy.sh   # 密码经环境变量临时注入，用完即删
```

**拓扑**：前端 `frontend/dist` → `http.server` SPA（端口 8000，systemd `qap-frontend`）；后端 `backend/` → `uvicorn app.main:app`（端口 8001，systemd `qap-backend`）。

常用变量覆盖：

| 变量 | 说明 |
|------|------|
| `DEPLOY_HOST` | 目标服务器（默认 `120.55.84.80`） |
| `FRONTEND_PORT` / `BACKEND_PORT` | 前后端端口（默认 8000 / 8001） |
| `SKIP_BACKEND=1` | 只部署前端（后端依赖未就绪时） |
| `VITE_USE_MOCK=false` | 前端切真实后端联调 |

---

## 添加工具

1. 写 `backend/tools/<工具名>/runner.py`，定义纯函数（返回字符串）
2. 在 `backend/tools/register_all.py` 注册：`registry.register_function(name, desc, schema, func)`
3. 需要时在 `backend/agent/prompts/planner_prompt.txt` 补充用法说明

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

FastAPI + SSE · LangGraph · Milvus · Redis · Docker Compose · Go 认证网关 · Vue 3 + Vite + Pinia · loguru · DeepSeek LLM

---

## License

MIT
