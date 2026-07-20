# Quantum Agent Platform

An LLM-driven autonomous platform for computational chemistry research, orchestrating quantum chemistry tools (EqV2, Gaussian, Multiwfn) through a LangGraph-based agent workflow.

## Architecture

- **app/** - FastAPI entry point and API routes
- **agent/** - Core agent (Planner, Executor, Critic, State machine)
- **workflow/** - LangGraph DAG workflow orchestration
- **tools/** - Computational chemistry tool wrappers (EqV2, Gaussian, Multiwfn)
- **rag/** - Knowledge retrieval system (embedding, Milvus, chunking)
- **llm/** - LLM client abstraction (Qwen/Ollama)
- **llmops/** - Observability (logging, caching, tracing, evaluation)
- **db/** - Data layer (Redis, Milvus, models)
- **config/** - Global configuration (YAML + env)

## Setup
启动步骤
第一步：启动基础设施（Docker）

docker-compose up -d
这会拉起 Milvus 向量数据库（及其依赖的 etcd + MinIO），大概需要 30-60 秒。验证：


docker ps
# 应该看到 milvus-standalone, milvus-etcd, milvus-minio 三个容器在运行
Milvus 用于 RAG 知识库检索，如果你不需要 RAG 功能可以不启它。

第二步：启动 FastAPI 服务

uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
或者用 Python 直接跑：


python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
第三步：打开前端
浏览器访问 http://localhost:8000，在对话框里输入任务即可。


出错反馈：重启服务（uvicorn app.main:app --reload 应该会自动 reload），然后再试同样的指令即可。