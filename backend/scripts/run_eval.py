import json
import sys

from rag.chunker import Chunker
from rag.embedder import Embedder
from rag.vector_db import MilvusClient
from rag.retriever import Retriever
from rag.ingestion import ingest_documents


def hit_count(retrieved_texts: list[str], keywords: list[str]) -> int:
    """统计有多少个关键词出现在检索结果中"""
    combined = " ".join(retrieved_texts).lower()
    return sum(1 for kw in keywords if kw.lower() in combined)


def evaluate(retriever: Retriever, queries: list[dict], top_k: int = 5) -> dict:
    """对一组查询做完整评估"""
    results = []
    total_keywords = 0
    found_keywords = 0
    queries_passed = 0

    for item in queries:
        query = item["query"]
        keywords = item["relevant_keywords"]
        retrieved = retriever.retrieve(query, top_k=top_k)
        retrieved_texts = [r["text"] for r in retrieved]

        hits = hit_count(retrieved_texts, keywords)
        total_keywords += len(keywords)
        found_keywords += hits
        if hits > 0:
            queries_passed += 1

        results.append({
            "query": query,
            "top_k": top_k,
            "keywords_expected": len(keywords),
            "keywords_found": hits,
            "retrieved_sources": [r["source"] for r in retrieved],
            "top_scores": [round(r["score"], 4) for r in retrieved[:3]],
        })

    n = len(queries)

    print("=" * 60)
    print(f"RAG 评估报告 (top_k={top_k})")
    print("=" * 60)
    print()

    for r in results:
        print(f"查询: {r['query']}")
        print(f"  关键词命中: {r['keywords_found']}/{r['keywords_expected']}  |  来源: {r['top_scores']}")
        print()

    print("-" * 60)
    print(f"整体指标:")
    print(f"  关键词召回率:      {found_keywords}/{total_keywords} = {found_keywords/total_keywords:.1%}")
    print(f"  查询成功率(>=1命中): {queries_passed}/{n} = {queries_passed/n:.1%}")
    print(f"  平均关键词命中/查询:  {found_keywords/n:.1f}")
    print("=" * 60)

    return {
        "keyword_recall": found_keywords / total_keywords if total_keywords else 0,
        "query_success_rate": queries_passed / n if n else 0,
        "avg_hits_per_query": found_keywords / n if n else 0,
        "details": results,
    }


def main():
    top_k = int(sys.argv[1]) if len(sys.argv) > 1 else 5

    # 1. 先入库（如果已经入过可以跳过这步）
    chunker = Chunker(chunk_size=512, overlap=50)
    embedder = Embedder()
    vector_db = MilvusClient()
    retriever = Retriever(embedder, vector_db)

    file_paths = ["data/quantum_basics.txt"]
    print("正在入库文档...")
    ingest_documents(file_paths, chunker, embedder, vector_db)
    print()

    # 2. 加载测试查询
    with open("data/eval_queries.json", encoding="utf-8") as f:
        queries = json.load(f)
    print(f"加载了 {len(queries)} 条测试查询\n")

    # 3. 评估
    evaluate(retriever, queries, top_k=top_k)


if __name__ == "__main__":
    main()
