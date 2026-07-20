"""
Agent 主入口 — 把所有组件串起来

启动时做的事（只做一次）：
  1. 创建 LLM 客户端
  2. 注册全部工具到 ToolRegistry
  3. 创建 MCPClient（持有 ToolRegistry）
  4. 创建 Planner / Executor / Critic / Retriever
  5. 用 LangGraph 把四个组件编成 DAG
  6. invoke() 运行

调用链（一次请求）：
  RAG 节点    → Retriever.retrieve_as_context()
  Plan 节点   → Planner.plan()           → LLM 拆解任务
  Exec 节点   → Executor.execute()       → MCPClient.call() → ToolRegistry.call() → 真工具函数
  Critic 节点 → Critic.review()          → LLM 判断是否通过
  路由        → 通过→END / 不通过→重试 Exec
"""

from agent.mcp_client import MCPClient
from agent.executor import Executor
from agent.planner import Planner
from agent.critic import Critic
from agent.state import AgentState
from llm.client import LLMClient

from tools.register_all import build_registry

# RAG 组件
from rag.embedder import Embedder
from rag.vector_db import MilvusClient as MilvusDB
from rag.retriever import Retriever

# LangGraph 工作流
from workflow.graph import build_workflow


def build_agent(use_rag: bool = True):
    """
    构建 Agent 的所有组件并返回编译好的 LangGraph workflow。

    这个函数只在进程启动时调一次。
    """

    # ── 第 1 层：LLM（Planner 和 Critic 共用）────────
    llm = LLMClient()
    print(f"[agent] LLM ready: {llm.model}")

    # ── 第 2 层：工具系统 ────────────────────────────
    registry = build_registry()          # 往 dict 里注册 10 个工具
    mcp = MCPClient(registry)            # 工具调用入口
    print(f"[agent] Tools registered: {len(registry._tools)}")

    # ── 第 3 层：Agent 核心组件 ──────────────────────
    planner = Planner(llm)
    executor = Executor(mcp, llm=llm)    # llm 用于 reasoning 步骤
    critic = Critic(llm)

    # ── 第 4 层：RAG 检索（可选）────────────────────
    retriever = None
    if use_rag:
        try:
            embedder = Embedder()
            milvus_db = MilvusDB()
            retriever = Retriever(embedder, milvus_db)
            print("[agent] RAG retriever ready (Milvus)")
        except Exception as e:
            print(f"[agent] RAG 不可用（Milvus 没启动？）: {e}")
            print("[agent] 将继续运行，但不使用知识库检索")

    # ── 第 5 层：LangGraph 编排 ─────────────────────
    workflow = build_workflow(
        planner=planner,
        executor=executor,
        critic=critic,
        retriever=retriever,
    )
    print("[agent] LangGraph workflow compiled")

    return workflow


def main():
    """演示一次完整的 Agent 调用"""
    print("=" * 60)
    print("  Quantum Agent Platform — 启动中")
    print("=" * 60)

    workflow = build_agent(use_rag=True)

    # ── 用户输入 ────────────────────────────────────
    user_query = "看看当前目录下有哪些 Python 文件，然后创建一个 test.txt 写入 hello world"

    print()
    print(f"用户: {user_query}")
    print()

    # ── 运行 LangGraph 工作流 ────────────────────────
    # invoke() 会自动走 RAG → Plan → Exec → Critic → (retry or END)
    final_state = workflow.invoke({
        "task_id": "demo-001",
        "user_query": user_query,
        "retry_count": 0,
    })

    # ── 输出结果 ────────────────────────────────────
    print()
    print("=" * 60)
    print("  最终结果")
    print("=" * 60)
    print(f"状态: {final_state.get('status')}")
    print(f"思考: {final_state.get('thinking', '')[:200]}...")
    print(f"计划步骤数: {len(final_state.get('plan', []))}")
    for i, step in enumerate(final_state.get("plan", [])):
        print(f"  Step {i}: {step.get('type')} → {step.get('step')} ({step.get('action')})")
    print(f"执行结果数: {len(final_state.get('results', []))}")
    for i, r in enumerate(final_state.get("results", [])):
        output = r.get("output", {})
        if isinstance(output, dict):
            status = output.get("status", "?")
            tool = output.get("tool", "?")
            result_preview = str(output.get("result", ""))[:100]
            print(f"  Result {i}: [{status}] {tool} → {result_preview}")
        else:
            print(f"  Result {i}: {str(output)[:100]}")
    print(f"重试次数: {final_state.get('retry_count', 0)}")

    # 清理测试文件
    import os
    if os.path.exists("test.txt"):
        os.remove("test.txt")
        print("\n(已清理 test.txt)")


if __name__ == "__main__":
    main()
