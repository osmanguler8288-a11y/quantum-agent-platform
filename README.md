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

```bash
pip install -r requirements.txt
python scripts/ingest_docs.py
uvicorn app.main:app --reload
```
