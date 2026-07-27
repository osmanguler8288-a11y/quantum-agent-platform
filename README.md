# Quantum Agent Platform

LLM 驱动的量子化学自主 Agent 平台。通过 **LangGraph 工作流**编排量子化学工具（Gaussian、Multiwfn、EqV2），集成 **RAG 知识检索**、**SSE 流式反馈**、**多轮对话记忆**、**Go 认证网关（登录/注册 + JWT）**和**自动重试机制**。

---

## 快速开始

### 前置条件

- **Docker & Docker Compose**
- **LLM API Key**（DeepSeek / OpenAI 兼容接口）

### 3 分钟跑起来

```bash
# 1. 克隆项目
git clone <repo-url> && cd quantum-agent-platform

# 2. 配置 API Key
cp .env.example .env
vim .env   # 填 LLM_API_KEY 和 EMBED_API_KEY

# 3. 启动全部服务
docker compose up -d

# 4. 打开浏览器 → 注册账号 → 登录 → 使用
# → http://localhost:8000
```

Docker Compose 会一键启动：Auth 网关 + App + MySQL + Redis + Milvus + etcd + MinIO。首次构建 Go 镜像需要几分钟，之后秒启。

### 开发模式

```bash
# 只起基础设施
docker compose up -d redis standalone mysql

# 手动跑 FastAPI
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 & 

# 手动跑 Go 认证服务
cd auth && go run . &
```

# 手动启动 FastAPI（--reload 热重载）
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

---

## 整体架构

```
用户浏览器 → Go 认证网关 → FastAPI → LangGraph → LLM / Tools
              │    :8080      :8000
              ├── /api/auth/register  (公开)
              ├── /api/auth/login     (公开)
              └── /api/*              (需 JWT，验证后转发)
              │
          MySQL :3306
        (用户表：id, username, password_hash, email)
```

```
用户浏览器                                         后端服务（Docker Compose）
─────────                                         ─────────────────────────

┌──────────┐    POST /api/*   Authorization: Bearer <JWT>
│ 前端 SPA │ ──→ Go Auth (:8000) ──→ FastAPI (qap-app)
│          │◄── SSE 流式事件 ─────────────────│
└──────────┘                                   │  LangGraph DAG:      │
                                               │  RAG → Plan →        │
                                               │  Execute → Critic    │
                                               └──────┬───────────────┘
                                                      │
            ┌──────────┬──────────┬──────────────────┼──────────┬──────────┐
            │          │          │                  │          │          │
       ┌────▼────┐┌────▼────┐┌────▼────┐      ┌─────▼─────┐┌────▼────┐┌────▼────┐
       │  MySQL  ││  Redis  ││ Milvus  │      │ DeepSeek  ││SiliconFlow││ 外部工具 │
       │  用户表  ││ 会话记忆 ││ 向量检索 │      │   LLM     ││ Embedding ││ Gaussian │
       └─────────┘└─────────┘└─────────┘      └───────────┘└──────────┘└─────────┘
```

### 工作流四阶段

| 阶段 | 节点 | 作用 |
|------|------|------|
| **0. RAG** | Retriever | 用户问题向量化 → Milvus 相似搜索 → 返回知识片段 |
| **1. Plan** | Planner | LLM 把任务拆成 JSON 可执行步骤，SSE 实时推送思考过程 |
| **2. Execute** | Executor | 逐条调工具，失败自动重试 3 次，每步实时推送状态 |
| **3. Critic** | Critic | LLM 评审结果 → 通过结束 / 不通过回到阶段 2（最多 3 轮） |

### 多轮对话

基于 Redis 的会话记忆：每个浏览器自动分配 `session_id`，对话历史存在 Redis（TTL=1 小时，每次对话刷新）。刷新页面或重新打开浏览器都能恢复上下文。

---

## 项目结构

```
quantum-agent-platform/
├── app/                        # FastAPI 应用
│   ├── main.py                 # 入口：创建实例 + 注册路由 + 静态文件
│   ├── routes/
│   │   ├── workflow.py         # ★ Agent 工作流 API（SSE 流式 + 一次性）
│   │   └── chat.py             # 纯 LLM 对话 API（不过工作流）
│   ├── schemas/request.py      # Pydantic 请求模型
│   └── static/index.html       # 前端页面（原生 HTML/CSS/JS）

├── agent/                      # Agent 核心
│   ├── planner.py              # 任务拆解 → JSON 步骤计划
│   ├── executor.py             # 计划执行 + 重试 + 流式
│   ├── critic.py               # 结果评审（LLM 判定 pass/fail）
│   ├── mcp_client.py           # 统一工具调用入口（本地 + 远程预留）
│   ├── state.py                # Agent 状态机（PENDING→PLANNING→...→DONE）
│   └── prompts/                # Planner / Critic 的系统提示词模板

├── tools/                      # 12 个内置工具
│   ├── register_all.py         # ★ 一键注册所有工具 → build_client()
│   ├── tool_register.py        # Tool 数据类 + ToolRegistry 注册中心
│   ├── bash/runner.py          # Shell 命令
│   ├── file_tools/runner.py    # 文件读写/列表/删除
│   ├── python_repl/runner.py   # Python 沙箱
│   ├── grep_tool/runner.py     # 正则搜索（内置 Gaussian 预设）
│   ├── gaussian/runner.py      # Gaussian 16 提交
│   ├── multiwfn/runner.py      # Multiwfn 波函数分析
│   ├── eqv2/runner.py          # EqV2 构象搜索
│   ├── humo_lumo/runner.py     # HOMO-LUMO 能隙提取
│   └── dip/runner.py           # 偶极矩/四极矩提取

├── rag/                        # RAG 知识检索
│   ├── embedder.py             # 文本 → 向量（调用 Embedding API）
│   ├── vector_db.py            # Milvus 客户端
│   ├── retriever.py            # 串联：embed → search → 格式化
│   ├── chunker.py              # 文档切分
│   └── ingestion.py            # 文档入库流水线

├── workflow/                   # LangGraph 编排
│   ├── graph.py                # 构建 DAG + 条件路由
│   └── nodes/                  # rag / plan / exec / critique 节点

├── llm/client.py               # LLM 调用（OpenAI 兼容，支持流式）
├── db/redis_client.py          # Redis 会话存储
├── config/settings.py          # 环境变量配置

├── auth/                       # Go 认证网关
│   ├── main.go                 # 登录/注册 + JWT + 反向代理
│   ├── Dockerfile              # 多阶段构建
│   └── go.mod
├── Dockerfile                  # Python App 镜像
├── docker-compose.yml          # 全栈编排（auth + app + mysql + redis + milvus）
├── .dockerignore
├── .env.example                # 环境变量模板（无密钥）
├── requirements.txt
└── README.md
```

---

## 12 个内置工具

| 工具 | 功能 | 关键参数 |
|------|------|----------|
| `bash` | 执行 Shell 命令 | `command`（必填）、`cwd`、`timeout` |
| `read_file` | 读取文件 | `path`（必填）、`max_lines` |
| `write_file` | 写入/创建文件 | `path`（必填）、`content`（必填） |
| `list_dir` | 列出目录 | `path`、`pattern`（如 `*.gjf`） |
| `delete_file` | 删除文件 | `path`（必填） |
| `python_repl` | Python 沙箱 | `code`（必填）、`timeout` |
| `grep_file` | 正则搜索 | `path`（必填）、`pattern`、`preset`（9 种量化预设） |
| `gaussian` | Gaussian 16 计算 | `input_file`（必填）、`output_file`（必填） |
| `multiwfn` | Multiwfn 波函数分析 | `input_file`（必填）、`commands`（必填） |
| `eqv2` | EqV2 构象搜索 | `input_file`（必填）、`output_file`（必填） |
| `homo_lumo` | HOMO/LUMO 能隙提取 | `fchk_path`（必填）、`num_around` |
| `dipole` | 偶极矩提取 | `out_path`（必填）、`extract_quadrupole` |

---

## API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/` | Web 前端 |
| `POST` | `/api/workflow/stream` | **Agent 工作流** — SSE 流式 |
| `POST` | `/api/workflow/run` | Agent 工作流 — 一次性返回 |
| `POST` | `/api/chat/stream` | 纯 LLM 对话 — SSE 流式 |
| `POST` | `/api/chat/` | 纯 LLM 对话 — 一次性返回 |
| `GET` | `/api/health/server` | 健康检查 |

SSE 事件类型：

```
thinking_chunk   → Planner 思考过程（逐 token）
plan_done        → 任务计划生成完成
step_start       → 开始执行工具
step_done        → 工具执行完成
verdict_done     → Critic 评审结果
retry            → 失败重试
done             → 工作流完成
error            → 异常（优雅降级）
```

---

## 配置

所有配置通过 `.env` 文件设置：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `LLM_MODEL` | `deepseek-chat` | LLM 模型 |
| `LLM_BASE_URL` | `https://api.deepseek.com` | LLM API 地址 |
| `LLM_API_KEY` | — | **必填** |
| `EMBED_MODEL` | `BAAI/bge-large-zh-v1.5` | Embedding 模型 |
| `EMBED_BASE_URL` | `https://api.siliconflow.cn/v1` | Embedding API 地址 |
| `EMBED_API_KEY` | — | **必填**（RAG 需要） |
| `REDIS_HOST` | `localhost` | Docker 里自动改为 `redis` |
| `MILVUS_HOST` | `localhost` | Docker 里自动改为 `standalone` |
| `MAX_RETRIES` | `3` | 失败最大重试轮数 |
| `MAX_STEPS` | `20` | 单次任务最大步骤数 |
| `TOP_K` | `5` | RAG 返回条数 |

---

## 如何添加工具

1. 写 `tools/<工具名>/runner.py`，定义纯函数
2. 在 `tools/register_all.py` 里 `registry.register_function("工具名", 描述, 参数Schema, 函数)`
3. 如果有需要 LLM 注意的用法，在 `agent/prompts/planner_prompt.txt` 里补充说明

```python
# 标准 runner 函数签名
def run_your_tool(required_param: str, optional_param: bool = False) -> str:
    """一句话描述"""
    # 干活
    return "格式化结果字符串"
```

---

## 部署

### 给自己或同事用

```bash
git clone <repo-url> && cd quantum-agent-platform
cp .env.example .env   # 填 API Key
docker-compose up -d
# 浏览器打开 http://localhost:8000
```

### 部署到云服务器

```bash
# 1. 云服务器装好 Docker
# 2. 同样三步：
git clone <repo-url> && cd quantum-agent-platform
cp .env.example .env && vim .env
docker-compose up -d

# 3. 开放 8000 端口，配置 nginx 反代 + SSL（可选）
```

### 注意事项

- **LLM API Key 是消耗品** — 如果想公网开放，务必加认证层，避免你的 key 被刷爆
- **量子化学工具需额外安装** — Gaussian/Multiwfn/EqV2 因许可证和体积未打包进镜像，需要时可挂载 volume 注入
- **Redis 会话 TTL=1 小时** — 对话历史在 1 小时无活动后自动清除

---

## 优雅降级

服务启动时会自动检测依赖是否可用，不可用不会崩溃：

| 依赖 | 不可用时的影响 |
|------|---------------|
| Redis 未启动 | LLM 对话正常，无多轮记忆 |
| Milvus 未启动 | LLM 对话正常，无 RAG 检索 |
| 全都没开 | LLM 对话依然正常 |

---

## 技术栈

| 层 | 技术 |
|----|------|
| Web 框架 | FastAPI + SSE Streaming |
| 工作流编排 | LangGraph (StateGraph DAG) |
| LLM | DeepSeek / OpenAI 兼容 API |
| 向量库 | Milvus 2.4 |
| 会话记忆 | Redis (session_id key, TTL=3600s) |
| 容器化 | Docker + Docker Compose |
| 前端 | 原生 HTML/CSS/JS |

---

## License

MIT
