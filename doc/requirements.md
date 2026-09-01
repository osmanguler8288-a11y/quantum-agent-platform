# 量子化学 Agent 产品需求文档（PRD）

> 版本：v2.0
> 更新：2026-08-16
> 说明：以**需求**为核心，每条需求都落到「前端页面/组件 + 对应接口」，前端据此开发，后端据此实现接口。

---

## 一、产品概述

### 1.1 产品定位

量子化学 Agent 是一个 **LLM 驱动的计算化学助手**。用户用自然语言描述计算任务，Agent 自动完成分子建模、计算调度、结果解析、物理解读与可视化。

### 1.2 核心价值

| 价值点 | 说明 |
|--------|------|
| 降低门槛 | 不用手写输入文件，自然语言即可发起计算 |
| 自动化 | 写输入、跑程序、翻日志、找数值、画图全自动 |
| 智能纠错 | 结果自动校验，失败自动重试并修正 |
| 上下文记忆 | 记住用户的分子、基组偏好，支持"换基组重算"类追问 |

### 1.3 产品边界

- **做**：量子化学计算任务的发起、执行、结果解读、可视化
- **不做**：非量子化学的通用聊天（礼貌引导回正题）、实验数据管理、文献管理

---

## 二、技术栈（已确定）

### 2.1 前端（本次开发主体）

| 项 | 选型 | 说明 |
|----|------|------|
| 框架 | **Vue 3**（Composition API + `<script setup>`） | 响应式天然适合聊天流 UI |
| 构建 | **Vite** | 开发热更新 + 产物构建 |
| 语言 | **TypeScript** | 类型安全，接口契约可复用 |
| 路由 | **Vue Router** | 登录页 / 主对话页 |
| 状态 | **Pinia** | 认证态、会话态、SSE 流状态 |
| 可视化 | **ECharts** | 光谱曲线、轨道能级图 |
| 分子渲染 | **3Dmol.js** | 3D 分子结构 |
| UI 组件 | 自定义 CSS（沿用橙色主题）+ Element Plus（表单/弹层/表格） | 可选，按需引入 |

> 部署：Vite 构建产物由 FastAPI 静态托管（沿用现有 Go 网关 → FastAPI 单服务架构）。开发期用 Vite dev server 代理 `/api` 到 FastAPI。

### 2.2 后端（沿用）

| 层 | 选型 |
|----|------|
| 应用 | FastAPI |
| 认证网关 | Go（JWT + 反向代理） |
| 数据库 | MySQL（用户）/ Redis（短期对话）/ Milvus（长期记忆 + RAG） |
| LLM | DeepSeek（OpenAI 兼容） |
| Embedding | OpenAI text-embedding-3-small |

---

## 三、目标用户与核心场景

### 3.1 用户画像

- 计算化学研究人员、课题组学生
- 熟悉 Gaussian / Multiwfn / 构象搜索，但不擅长编程
- 希望把重复性的"写输入、跑程序、找数值、画图"交给 Agent

### 3.2 核心场景

| 编号 | 场景 | 用户输入示例 | 期望产出 |
|------|------|-------------|---------|
| S1 | 结构优化 | "优化苯的结构，B3LYP/6-31G*" | 3D 结构 + 能量 |
| S2 | 单点能 | "算甲醛的单点能" | 能量 + 偶极矩 |
| S3 | 频率分析 | "算甲醇的红外光谱" | IR 谱图 + 热力学量 |
| S4 | HOMO/LUMO | "算这个分子的 HOMO-LUMO 能隙" | 能级图 + gap |
| S5 | 激发态 | "算吸收光谱，TD-DFT" | 吸收谱 + 激发态列表 |
| S6 | 构象搜索 | "搜索正丁烷的构象" | 构象列表 + 能量排序 |
| S7 | 波函数分析 | "做 ESP 静电势分析" | ESP 图 + 数值 |
| S8 | 过渡态 | "找这个反应的过渡态" | 结构 + 虚频验证 |
| S9 | 溶剂效应 | "算水溶液中的单点能" | 溶剂化能 |
| S10 | 上下文追问 | "把基组换成 def2-TZVP 再算一次" | 复用分子结构，只改基组 |

---

## 四、功能地图

```
量子化学 Agent
├── 1. 账号体系
│   ├── 注册 / 登录 / 退出
│   └── 登录态保持 + 防重复注册
├── 2. 对话交互
│   ├── 发送消息 + 流式接收
│   ├── 多轮对话 + 会话管理
│   ├── 输入建议 chips
│   └── 分子结构输入（XYZ/SMILES/上传）
├── 3. 任务执行可视化
│   ├── 思考过程（可折叠）
│   ├── 计划步骤展示
│   ├── 步骤执行状态
│   └── 评审结论
├── 4. 结果展示
│   ├── 数值卡
│   ├── 轨道能级图
│   ├── 光谱曲线
│   ├── 3D 分子结构
│   └── 产物下载
├── 5. 工具体系
│   ├── 工具清单展示
│   └── 工具调用（经对话触发）
└── 6. 记忆中心
    ├── 长期记忆查看
    ├── 记忆筛选
    └── 手动整合 / 遗忘
```

---

## 五、详细功能需求

> 每条需求标注：优先级（P0 必须有 / P1 重要 / P2 可选）、前端落点、对应接口。

### 5.1 账号体系

| 需求ID | 需求描述 | 前端组件 | 对应接口 | 优先级 |
|--------|---------|---------|---------|--------|
| A1 | 用户注册：输入用户名/邮箱/密码，创建账号 | AuthView 注册表单 | `POST /api/auth/register` | P0 |
| A2 | 用户登录：输入用户名/密码 | AuthView 登录表单 | `POST /api/auth/login` | P0 |
| A3 | 退出登录：清空本地 token，回到登录页 | Header 退出按钮 | 前端清 token（无后端） | P0 |
| A4 | 登录态保持：刷新页面仍保持登录 | Pinia store + localStorage | 无（读本地 token） | P0 |
| A5 | 防重复注册：用户名/邮箱已存在时提示 | AuthView 错误提示区 | 复用 `POST /api/auth/register`（后端返回错误） | P0 |
| A6 | 表单校验与错误提示：必填/格式错误/后端错误统一展示 | AuthView 错误提示区 | 同上 | P0 |

**交互流程**：

```
未登录 → 显示 AuthView（登录/注册切换）
登录成功 → 存 token → 进入 ChatView
token 失效（401）→ 自动登出 → 回 AuthView
```

**错误提示需求（A5/A6 关键）**：
- 用户名/密码为空 → 前端即时提示"请填写用户名和密码"
- 后端返回"该用户名已注册"/"该邮箱已被注册" → 展示在表单上方红色提示
- 网络异常 → "无法连接到服务器"
- 请求期间按钮禁用 + loading 态

---

### 5.2 对话交互

| 需求ID | 需求描述 | 前端组件 | 对应接口 | 优先级 |
|--------|---------|---------|---------|--------|
| C1 | 发送消息：输入任务描述，回车或点发送 | InputBar | `POST /api/workflow/stream` | P0 |
| C2 | 流式接收：实时显示思考/计划/步骤/结果 | ChatArea（SSE 解析） | `POST /api/workflow/stream`（SSE） | P0 |
| C3 | 多轮对话：带 session_id 维持上下文 | Pinia session store | `POST /api/workflow/stream`（body 带 session_id） | P0 |
| C4 | 会话管理：新建会话/清除会话 | Header 会话 badge | 前端重置 session_id | P0 |
| C5 | 输入建议：常见任务一键填充 | SuggestionChips | 无（纯前端） | P1 |
| C6 | 分子结构输入：粘贴 XYZ / 输入 SMILES / 上传文件 | StructureInput（弹层或输入框附件） | 随 C1 一起提交 | P1 |

**C6 分子结构输入交互**：

```
输入框旁「结构」按钮 → 弹出 StructureInput
  ├── 粘贴 XYZ 坐标（文本框）
  ├── 输入 SMILES（如 c1ccccc1）
  └── 上传 .xyz / .mol 文件
→ 结构随 user_query 一起提交，Agent 在 planner 阶段建模
```

**C2 流式接收流程**：前端用 `fetch + ReadableStream` 解析 SSE（因现有接口是 POST 型 SSE，非 EventSource）。

---

### 5.3 任务执行可视化

| 需求ID | 需求描述 | 前端组件 | SSE 事件 | 优先级 |
|--------|---------|---------|---------|--------|
| T1 | 思考过程：逐字显示 LLM 思考，可折叠 | ThinkingBlock | `thinking_chunk` | P0 |
| T2 | 计划步骤：展示拆解出的步骤列表（工具名 + 参数） | PlanCard | `plan_done` | P0 |
| T3 | 执行状态：每步 running → done/fail 徽标 | StepStatusRow | `step_start` / `step_done` | P0 |
| T4 | 评审结论：pass/fail + 解读 + 修复建议 | VerdictCard | `verdict_done` | P0 |
| T5 | 重试提示：失败重试进度 | RetryBanner | `retry` | P1 |

**前端交互状态机**：

```
idle ──提交──> thinking ──> planning ──> executing ──> reviewing ──> done
                  │             │            │              │
                  │             └──(空计划)──┴──────────────┘→ done
                  └──────────────────────────────> error
```

| 状态 | 前端表现 |
|------|---------|
| idle | 输入框可编辑，发送按钮可点 |
| thinking | 按钮禁用 + spinner，思考文本逐字出现 |
| planning | plan 卡片逐步渲染 |
| executing | 每步 running → done/fail |
| reviewing | 评审卡片 |
| done / error | 恢复按钮，更新会话 badge / 红色错误气泡 |

---

### 5.4 结果展示

| 需求ID | 需求描述 | 前端组件 | 数据来源 | 优先级 |
|--------|---------|---------|---------|--------|
| R1 | 数值卡：能量/偶极矩/能隙等单一数值 | NumberCard | `result_viz`（type=dipole/energy） | P1 |
| R2 | 轨道能级图：HOMO/LUMO 及附近轨道 | OrbitalDiagram（ECharts） | `result_viz`（type=homo_lumo） | P1 |
| R3 | 光谱曲线：吸收/发射/红外 | SpectrumPlot（ECharts） | `result_viz`（type=tddft/freq） | P1 |
| R4 | 3D 分子结构：可旋转缩放球棍模型 | Molecule3D（3Dmol.js） | `result_viz`（type=structure） | P1 |
| R5 | 产物下载：.log/.fchk/谱图等 | DownloadLink | `GET /api/workflow/artifacts/{task_id}/{filename}` | P2 |

**结果展示依赖一个新增 SSE 事件 `result_viz`**，前端按 `type` 字段分发到对应可视化组件：

```jsonc
{"event":"result_viz","data":{"type":"homo_lumo","homo_e":-0.25,"lumo_e":-0.05,"gap_eV":5.4,"orbitals":[...]}}
{"event":"result_viz","data":{"type":"dipole","components":{"x":0.1,"y":0.2,"z":0.0,"tot":0.22}}}
{"event":"result_viz","data":{"type":"tddft","states":[{n,energy_eV,wavelength_nm,osc_strength,transitions}]}}
{"event":"result_viz","data":{"type":"structure","atoms":[{symbol,x,y,z}]}}
```

> 前端先按这些结构用 mock 数据搭组件，后端后续补 `result_viz` 事件。

---

### 5.5 工具体系

| 需求ID | 需求描述 | 前端组件 | 对应接口 | 优先级 |
|--------|---------|---------|---------|--------|
| L1 | 工具清单展示：展示平台可用的量化/系统/记忆工具 | ToolPanel（侧栏或弹层） | `GET /api/tools`（新增，可选） | P2 |
| L2 | 工具调用：通过对话自然触发，执行过程在 T3 展示 | StepStatusRow | 经 `POST /api/workflow/stream` | P0 |

**说明**：工具调用对用户透明——用户在对话里描述任务，Agent 自动选工具，前端只负责展示执行状态（T3），不需要用户手动点工具。

---

### 5.6 记忆中心

| 需求ID | 需求描述 | 前端组件 | 对应接口 | 优先级 |
|--------|---------|---------|---------|--------|
| M1 | 长期记忆查看：展示当前用户积累的记忆 | MemoryPanel（弹层） | `GET /api/workflow/history` | P1 |
| M2 | 记忆筛选：按类型（working/episodic/semantic/perceptual）与重要性过滤 | MemoryPanel 筛选器 | 复用 M1（前端过滤或接口参数） | P2 |
| M3 | 手动整合：episodic → semantic | MemoryPanel 操作按钮 | `POST /api/workflow/memory/consolidate` | P2 |
| M4 | 手动遗忘：清理低重要性记忆 | MemoryPanel 操作按钮 | `POST /api/workflow/memory/forget` | P2 |

**M1 记忆展示字段**：类型标签、内容预览、重要性、时间戳。

---

### 5.7 知识库 RAG（可选，P2）

| 需求ID | 需求描述 | 前端组件 | 对应接口 | 优先级 |
|--------|---------|---------|---------|--------|
| K1 | 文档上传入库 | KnowledgePanel | `POST /api/rag/ingest`（新增） | P2 |
| K2 | 知识库文档列表 | KnowledgePanel | `GET /api/rag/documents`（新增） | P2 |

> 本模块当前后端只支持脚本 ingest（scripts/ingest_docs.py），无 Web 接口，前端可后置。

---

## 六、页面与路由

| 路由 | 页面 | 说明 |
|------|------|------|
| `/login` | AuthView | 登录/注册（未登录时唯一入口） |
| `/` | ChatView | 主对话页（核心） |
| `/settings` | SettingsView | 个人设置（可选，P2） |

**AuthView 与 ChatView 的关系**：应用启动时检查本地 token，有则进 ChatView，无则进 AuthView。全局路由守卫拦截未登录访问。

---

## 七、接口清单

### 7.1 REST API

| 方法 | 路径 | 用途 | 需求 |
|------|------|------|------|
| POST | `/api/auth/register` | 注册 | A1/A5 |
| POST | `/api/auth/login` | 登录 | A2 |
| POST | `/api/workflow/stream` | 工作流 SSE 流式 | C1/C2/C3 |
| POST | `/api/workflow/run` | 工作流一次性返回 | 备用 |
| POST | `/api/chat/stream` | 纯对话 SSE | 备用 |
| GET | `/api/workflow/history` | 长期记忆列表 | M1 |
| POST | `/api/workflow/memory/consolidate` | 手动整合 | M3 |
| POST | `/api/workflow/memory/forget` | 手动遗忘 | M4 |
| GET | `/api/health/server` | 健康检查 | — |
| GET | `/api/tools` | 工具清单（新增） | L1 |
| GET | `/api/workflow/artifacts/{task_id}/{filename}` | 产物下载（新增） | R5 |

### 7.2 SSE 事件（前端分发依据）

| 事件 | data 结构 | 前端落点 |
|------|----------|---------|
| `thinking_chunk` | `string` | ThinkingBlock |
| `plan_done` | `[{type,step,action,params}]` | PlanCard |
| `step_start` | `{index, step}` | StepStatusRow（running） |
| `step_done` | `{index, result}` | StepStatusRow（done/fail） |
| `verdict_done` | `{passed, reason, suggestions, comment}` | VerdictCard |
| `retry` | `{retry_count}` | RetryBanner |
| `memory_done` | `{count}` | 静默记录 |
| `rag_done` | `{context_len}` | 静默记录 |
| `result_viz` | `{type, ...}` | 可视化组件分发（新增） |
| `done` | `{status, session_id}` | 完成状态 |
| `error` | `{message}` | 错误气泡 |

---

## 八、非功能需求

| 类别 | 需求 |
|------|------|
| 安全 | JWT 认证、危险操作确认、API Key 不落库 |
| 可靠 | 工具重试、LLM 重试、任务超时、结构化日志 |
| 性能 | 流式首字延迟 < 2s（thinking 快速出字） |
| 成本 | Token 计数、响应缓存 |
| 可观测 | 每任务记录用时/步骤数/重试/token |
| 可扩展 | 工具注册表模式（已有） |

---

## 九、迭代计划

| 迭代 | 内容 | 依赖 |
|------|------|------|
| M1 | 前端骨架：Vue3+Vite 初始化、路由、AuthView、ChatView 布局 | 技术栈 |
| M2 | 账号体系（A1~A6）打通真实登录 | Go 网关已就绪 |
| M3 | 对话流 + 执行可视化（C1~C5, T1~T5）对接真实 SSE | FastAPI stream 已就绪 |
| M4 | 结果可视化（R1~R4）用 mock 数据搭组件 | 无（可独立） |
| M5 | 分子结构输入（C6）+ 记忆中心（M1~M4） | 记忆接口已就绪 |
| M6 | 后端补 `result_viz` 事件 + 产物下载 + 工具清单 | 前端契约已定 |

> 前端 M4（可视化组件）可与后端解耦，先按 `result_viz` 契约用 mock 数据开发。
