# 第一课：项目骨架搭建 + FastAPI 跑起来

## 本课目标

- 理解你项目的每个目录是干嘛的
- 理解 FastAPI 怎么定义接口、uvicorn 怎么启动服务
- 能自己新增一个路由，用 curl 验证

## 前置要求

- Python 3.9+（你已有）
- 已安装：`pip3 install fastapi uvicorn pydantic`（上节课装好了）

---

## 1.1 先看懂你的项目目录

你现在打开的项目 `quantum-agent-platform/` 长这样：

```
quantum-agent-platform/
├── app/                    # API 入口，对外暴露 HTTP 接口
│   ├── main.py             # FastAPI 实例创建 + 路由注册
│   ├── routes/             # 具体路由文件（chat、task、workflow）
│   │   ├── chat.py
│   │   ├── run_task.py
│   │   └── workflow.py
│   └── schemas/            # 请求/响应的数据结构
│       ├── request.py
│       └── response.py
│
├── agent/                  # Agent 核心（大脑），这课不讲
├── workflow/               # LangGraph 工作流，这课不讲
├── tools/                  # 工具层，这课不讲
├── rag/                    # 知识库，这课不讲
├── llm/                    # LLM 调用，这课不讲
├── llmops/                 # 可观测性，这课不讲
├── db/                     # 数据库，这课不讲
├── config/                 # 配置文件
├── data/                   # 数据文件（raw/processed/vectors）
├── scripts/                # 工具脚本
├── tests/                  # 测试
├── logs/                   # 日志
├── requirements.txt        # 依赖列表
├── COURSE.md               # 课程大纲
└── README.md
```

**关键概念——Python 的 import 路径：**

你现在在 `quantum-agent-platform/` 目录下运行程序。Python 把这个目录当作根路径。所以：

```python
from app.routes import chat        # 找 app/routes/chat.py
from agent.planner import Planner  # 找 agent/planner.py 里的 Planner 类
from tools.eqv2.runner import run_eqv2  # 找 tools/eqv2/runner.py 里的 run_eqv2 函数
```

每个目录下的 `__init__.py`（空文件）告诉 Python："这个目录是一个 package，可以 import"。没有这个文件 Python 找不到。

---

## 1.2 FastAPI 怎么工作的

### 最简例子

新建一个临时文件感受一下：

```python
# 最简 FastAPI 应用
from fastapi import FastAPI

app = FastAPI()  # 创建一个 FastAPI 实例，名字随便取

@app.get("/hello")           # 装饰器：当 GET /hello 请求进来时，执行下面这个函数
def say_hello():
    return {"msg": "hello"}  # 返回的 dict 自动转成 JSON

@app.get("/add/{a}/{b}")     # 路径参数：/add/3/5 → {"result": 8}
def add(a: int, b: int):     # FastAPI 自动把字符串 "3" 转成 int 3
    return {"result": a + b}
```

**装饰器 `@app.get("/hello")` 是什么？** 用 Go 类比：

```go
// Go
http.HandleFunc("/hello", sayHello)
```

```python
# Python — @app.get("/hello") 是语法糖，效果一样
@app.get("/hello")
def say_hello():
    return {"msg": "hello"}
```

`@` 是 Python 的装饰器语法，就是把下面的函数注册到路由表里。你不需要深究原理，当成"注册一个接口"就行。

### 你现在 main.py 的工作机制

打开 [app/main.py](../app/main.py)，逐行看：

```python
from fastapi import FastAPI
from app.routes import chat, run_task, workflow  # 把三个路由模块 import 进来

app = FastAPI(title="Quantum Agent Platform")    # 创建 FastAPI 实例

# 把子路由挂到主应用上
app.include_router(chat.router, prefix="/api/chat", tags=["chat"])
app.include_router(run_task.router, prefix="/api/task", tags=["task"])
app.include_router(workflow.router, prefix="/api/workflow", tags=["workflow"])

@app.get("/health")
async def health_check():
    return {"status": "ok"}
```

`include_router` 的意思是：把 `chat.py` 里定义的 `/` 路径，加上前缀 `/api/chat`。所以：
- chat.py 的 `@router.post("/")` → 实际路径是 `POST /api/chat/`
- run_task.py 的 `@router.post("/")` → 实际路径是 `POST /api/task/`

---

## 1.3 uvicorn 怎么把 FastAPI 变成服务

```bash
python3 -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

逐个拆解：

| 部分 | 含义 |
|------|------|
| `python3 -m uvicorn` | 用 Python 运行 uvicorn 模块（`-m` = module） |
| `app.main:app` | `app/main.py` 文件里的 `app` 变量 |
| `--reload` | 代码改了自动重启（开发用，部署时去掉） |
| `--host 0.0.0.0` | 监听所有网络接口 |
| `--port 8000` | 端口 8000 |

**流程：**
1. uvicorn 启动，监听 8000 端口
2. 它 import `app.main`，找到 `app = FastAPI(...)` 这个实例
3. 有 HTTP 请求进来 → uvicorn 把请求转成 Python 对象 → 交给 FastAPI
4. FastAPI 匹配路由 → 调用你的函数 → 返回值 → uvicorn 转成 HTTP 响应发回去

---

## 1.4 动手：新增一个自己的路由

打开 [app/routes/chat.py](../app/routes/chat.py)，当前内容：

```python
from fastapi import APIRouter

router = APIRouter()

@router.post("/")
async def chat():
    return {"message": "chat endpoint"}
```

我们来丰富一下它，让它真正接收用户消息并返回。

### 改造 chat.py

需要改三个文件：request schema、chat 路由、response schema。

**第一步：定义请求体** — 打开 [app/schemas/request.py](../app/schemas/request.py)，确认有：

```python
from pydantic import BaseModel

class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None  # 可选字段，不传就是 None
```

**Pydantic 是什么？** 用 Go 类比：

```go
// Go struct — 定义请求的字段和类型
type ChatRequest struct {
    Message   string  `json:"message"`
    SessionID *string `json:"session_id,omitempty"`
}
```

```python
# Python Pydantic — 效果一样，但自动校验 + 自动生成文档
class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None
```

Pydantic 做的事情：
1. 自动校验：传了 `{"message": 123}` 会报错（123 不是 str）
2. 自动生成 Swagger 文档（打开 `http://localhost:8000/docs` 能看到）
3. `str | None = None` 表示"可以不传，默认 None"

**第二步：改造路由** — 替换 [app/routes/chat.py](../app/routes/chat.py)：

```python
from fastapi import APIRouter
from app.schemas.request import ChatRequest
from app.schemas.response import ChatResponse

router = APIRouter()

@router.post("/", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """接收用户消息，返回回复"""
    reply = f"你说的是: {req.message}"  # f-string：花括号里放变量
    return ChatResponse(message=reply, session_id=req.session_id or "default")
```

**新东西讲解：**

`response_model=ChatResponse`：告诉 FastAPI 返回值要按 ChatResponse 格式序列化，自动生成文档。

`f"你说的是: {req.message}"`：f-string，Go 里是 `fmt.Sprintf("你说的是: %s", req.Message)`。

**第三步：重启服务**

```bash
# 先 Ctrl+C 停掉之前的
cd /Users/Zhuanz/Documents/quantum-agent-platform
python3 -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**第四步：用 curl 测试**

```bash
# POST 请求，Content-Type: application/json
curl -X POST http://localhost:8000/api/chat/ \
  -H "Content-Type: application/json" \
  -d '{"message": "优化乙醇结构"}'
```

预期返回：

```json
{"message": "你说的是: 优化乙醇结构", "session_id": "default"}
```

也可以用浏览器打开 `http://localhost:8000/docs`，Swagger 页面上直接点 "Try it out" 填参数测试。

---

## 1.5 Go ↔ Python 速查表（本课涉及的）

| 概念 | Go | Python |
|------|-----|--------|
| 定义变量 | `s := "hello"` | `s = "hello"` |
| 类型标注 | `var s string = "hello"` | `s: str = "hello"` |
| 结构体 | `type Req struct { Message string }` | `class Req(BaseModel): message: str` |
| 路由注册 | `http.HandleFunc("/", h)` | `@app.get("/")` 装饰器 |
| 启动服务 | `http.ListenAndServe(":8000", nil)` | `uvicorn app.main:app --port 8000` |
| 格式化字符串 | `fmt.Sprintf("x=%d", x)` | `f"x={x}"` |
| 可选/指针 | `*string` | `str \| None = None` |
| 字典/JSON | `map[string]interface{}` | `dict` |
| 列表 | `[]string{"a", "b"}` | `["a", "b"]` |

---

## 1.6 本课检查清单

- [ ] 能解释 `uvicorn app.main:app` 每一部分的含义
- [ ] 能说出 `app/` 下每个文件的作用
- [ ] 能在 `app/routes/` 下新建一个 `.py` 文件，定义一个路由
- [ ] 能在 `app/main.py` 里 `include_router` 挂上去
- [ ] 能打开 `http://localhost:8000/docs` 看到 Swagger 页面
- [ ] 能用 curl 请求自己的接口并看到正确返回

---

## 1.7 常见报错排错

| 报错 | 原因 | 解决 |
|------|------|------|
| `ModuleNotFoundError: No module named 'fastapi'` | 没装 | `pip3 install fastapi` |
| `ModuleNotFoundError: No module named 'app'` | 启动目录不对 | `cd` 到项目根目录再跑 |
| `Address already in use` | 8000 端口被占了 | 先 `Ctrl+C` 停旧进程，或换端口 `--port 8001` |
| `422 Unprocessable Entity` | 请求体格式不对 | 检查 JSON key 名是否和 Pydantic 字段名一致 |

---

下一课：[第二课：LLM Client 封装 + Prompt Engine](lesson-02-llm-client.md)
