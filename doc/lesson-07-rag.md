# 第七课：RAG 系统 — 知识入库与检索

## 本课目标

- 理解 RAG（Retrieval-Augmented Generation）的完整链路
- 实现文本切片（chunking）、向量化（embedding）、存储（Milvus）、检索（retrieval）
- 学会用 Python 调 embedding 模型
- 让 Agent 能"查资料"再做事

## 前置要求

- 第五课完成（Agent 闭环跑通，工具层可以先不真接）
- 安装：`pip3 install pymilvus openai`
- 安装 Milvus：`brew install milvus` 或 Docker `docker run -d --name milvus -p 19530:19530 milvusdb/milvus`（本节课可先用内存 dict 替代，不装也能学）

---

## 7.1 RAG 是什么，为什么要它

现在你的 Agent 拆任务全靠 Planner 自己的知识。但大模型不知道：
- 你们课题组用 B3LYP/def2-SVP 发现比文献的 B3LYP/6-31G(d) 效果好
- 某篇最新文献里建议用 wB97XD 算这类过渡态

**RAG = 做决策之前，先从知识库里检索相关资料，把它拼进 prompt。**

```
没有 RAG：
  用户任务 → Planner → Plan

有 RAG：
  用户任务 → Retriever（查资料）→ Planner（带资料思考）→ Plan
```

---

## 7.2 RAG 的五个环节

```
文档 → Chunker（切小块）→ Embedder（转向量）→ VectorDB（存库）
                                                      ↓
                                                  Retriever（查）
                                                      ↓
                                                  拼进 Prompt
```

每个环节对应你项目里的一个文件：
- `rag/chunker.py` — 切文本
- `rag/embedder.py` — 文本 → 向量
- `rag/vector_db.py` — 存储 + 搜索
- `rag/retriever.py` — 查询入口
- `rag/ingestion.py` — 批量入库脚本

---

## 7.3 Chunker：把长文档切成小块

为什么要切？embedding 模型一次只能处理几百字，一整篇论文塞不进去。

打开 [rag/chunker.py](../rag/chunker.py)，改成：

```python
class Chunker:
    """文本切片：把长文档切成可被 embedding 模型处理的小块"""

    def __init__(self, chunk_size: int = 512, overlap: int = 50):
        self.chunk_size = chunk_size
        self.overlap = overlap

    def chunk(self, text: str) -> list[dict]:
        """切分文本，返回 [{text, index, start, end}, ...]"""
        if len(text) <= self.chunk_size:
            return [{"text": text, "index": 0, "start": 0, "end": len(text)}]

        chunks = []
        start = 0
        idx = 0
        while start < len(text):
            end = min(start + self.chunk_size, len(text))
            chunk_text = text[start:end]
            chunks.append({
                "text": chunk_text,
                "index": idx,
                "start": start,
                "end": end,
            })
            idx += 1
            start += self.chunk_size - self.overlap  # 有重叠，避免切断关键信息
        return chunks
```

**重叠（overlap）是干嘛的？** 比如 `chunk_size=512, overlap=50`：

```
chunk0: [0:512]
chunk1:     [462:974]     ← 前50个字符和chunk0一样
chunk2:         [924:1436]
```

防止"B3LYP/def2-SVP 适合过渡态"这句话被切在 510-530 的位置，导致前半句在 chunk0，后半句在 chunk1，谁都看不懂。

`text[start:end]`：Python 的切片语法。`text[0:512]` 取前 512 个字符。注意区间是左闭右开 `[start, end)`。

---

## 7.4 Embedder：文本 → 向量

向量就是一组浮点数数组。两段文本语义越接近，它们向量的余弦相似度越高。

打开 [rag/embedder.py](../rag/embedder.py)：

```python
class Embedder:
    """文本转向量，支持 OpenAI 兼容 API"""

    def __init__(self, model_name: str = "text-embedding-3-small",
                 base_url: str = "https://api.openai.com/v1",
                 api_key: str = "sk-placeholder"):
        self.model_name = model_name
        self.base_url = base_url
        self.api_key = api_key

    def embed(self, texts: list[str]) -> list[list[float]]:
        """批量 embedding
        输入: ["优化苯结构", "计算HOMO"]
        输出: [[0.12, -0.34, ...], [0.45, 0.23, ...]]
        """
        # 如果没装 OpenAI SDK 或用本地模型，先返回假向量
        try:
            from openai import OpenAI
            client = OpenAI(api_key=self.api_key, base_url=self.base_url)
            response = client.embeddings.create(
                model=self.model_name,
                input=texts,
            )
            return [d.embedding for d in response.data]
        except Exception:
            # fallback：返回简单的哈希向量（开发调试用）
            print("[embedder] 远程 embedding 不可用，使用本地假向量")
            return [self._fallback_embed(t) for t in texts]

    def embed_query(self, query: str) -> list[float]:
        """单条查询 embedding"""
        return self.embed([query])[0]

    def _fallback_embed(self, text: str) -> list[float]:
        """假 embedding：基于字符哈希的确定性向量，开发调试用"""
        import hashlib
        h = hashlib.sha256(text.encode()).digest()
        # 把 32 字节哈希转成 8 个浮点数（真的 embedding 是 1536 维，这里简化）
        vals = []
        for i in range(0, 32, 4):
            val = int.from_bytes(h[i:i+4], "big") / (2**32)
            vals.append(val)
        return vals
```

**`try...except Exception` 里的 fallback 设计：** 开发时不依赖外部 API，用哈希生成假向量；部署时替换成真实 embedding。Go 程序员——这就是 "依赖注入" 的一种形式。

---

## 7.5 VectorDB：存储和搜索向量

你可以用 Milvus（生产环境），也可以用内存 dict（开发调试）。

打开 [rag/vector_db.py](../rag/vector_db.py)：

```python
import numpy as np


class VectorDB:
    """向量数据库封装。先用内存 dict，后续替换为 Milvus"""

    def __init__(self):
        self._store: list[dict] = []  # 每条: {vector, metadata, text}

    def insert(self, vectors: list[list[float]], texts: list[str],
               metadata: list[dict] = None):
        """批量插入"""
        if metadata is None:
            metadata = [{}] * len(vectors)

        for vec, txt, meta in zip(vectors, texts, metadata):
            self._store.append({
                "vector": vec,
                "text": txt,
                "metadata": meta,
            })

    def search(self, query_vector: list[float], top_k: int = 5) -> list[dict]:
        """返回最相似的 top_k 条，每条的 similarity 用余弦相似度"""
        results = []
        for item in self._store:
            sim = self._cosine_similarity(query_vector, item["vector"])
            results.append({
                "text": item["text"],
                "metadata": item["metadata"],
                "similarity": sim,
            })

        results.sort(key=lambda x: x["similarity"], reverse=True)
        return results[:top_k]

    def _cosine_similarity(self, a: list[float], b: list[float]) -> float:
        """余弦相似度：cos(θ) = a·b / (|a|*|b|)"""
        a_arr = np.array(a)
        b_arr = np.array(b)
        dot = np.dot(a_arr, b_arr)
        norm_a = np.linalg.norm(a_arr)
        norm_b = np.linalg.norm(b_arr)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(dot / (norm_a * norm_b))

    def count(self) -> int:
        return len(self._store)
```

**新概念讲解：**

`zip(vectors, texts, metadata)`：把三个列表"拉链"起来并行遍历。

```python
for v, t, m in zip([1,2], ["a","b"], ["x","y"]):
    print(v, t, m)
# 1 a x
# 2 b y
```

`results.sort(key=lambda x: x["similarity"], reverse=True)`：按 similarity 从高到低排序。`lambda x: x["similarity"]` 是匿名函数，Go 里就是 `func(x) float { return x.similarity }`。Python 可以一行写完：

```go
// Go
sort.Slice(results, func(i, j int) bool {
    return results[i].similarity > results[j].similarity
})
```

```python
# Python
results.sort(key=lambda x: x["similarity"], reverse=True)
```

`numpy` 两个方法：`np.dot`（点积）和 `np.linalg.norm`（向量长度）用来算余弦相似度。这是检索质量的核心。

---

## 7.6 Retriever：查询入口

打开 [rag/retriever.py](../rag/retriever.py)：

```python
class Retriever:
    """检索入口：接收查询 → embedding → 查向量库 → 返回文档"""

    def __init__(self, embedder, vector_db):
        self.embedder = embedder
        self.vector_db = vector_db

    def retrieve(self, query: str, top_k: int = 5) -> list[dict]:
        query_vec = self.embedder.embed_query(query)
        return self.vector_db.search(query_vec, top_k)

    def retrieve_as_context(self, query: str, top_k: int = 3) -> str:
        """检索结果直接拼成一段文本，可以塞进 prompt"""
        results = self.retrieve(query, top_k)
        if not results:
            return ""

        lines = ["## 参考资料"]
        for i, r in enumerate(results, start=1):
            lines.append(f"{i}. {r['text']} (相似度: {r['similarity']:.2f})")
        return "\n".join(lines)
```

`retrieve_as_context` 是后续跟 Planner 对接的关键方法——查完直接拼成 prompt 片段。

`f"{r['similarity']:.2f}"`：格式化浮点数为两位小数。Go：`fmt.Sprintf("%.2f", r.similarity)`。

`enumerate(results, start=1)`：从 1 开始编号（默认从 0）。

---

## 7.7 Ingestion：批量文档入库

打开 [rag/ingestion.py](../rag/ingestion.py)：

```python
from rag.chunker import Chunker


def ingest_documents(file_paths: list[str], chunker: Chunker,
                     embedder, vector_db):
    """批量文档入库：读文件 → 切块 → embedding → 存向量库"""
    for path in file_paths:
        print(f"[ingest] 处理: {path}")
        with open(path) as f:
            text = f.read()

        chunks = chunker.chunk(text)
        chunk_texts = [c["text"] for c in chunks]
        metadata = [{"source": path, "chunk_idx": c["index"]} for c in chunks]

        vectors = embedder.embed(chunk_texts)
        vector_db.insert(vectors, chunk_texts, metadata)

        print(f"[ingest] {path}: {len(chunks)} 个 chunk 已入库")
```

**列表推导式 `[c["text"] for c in chunks]`：** Python 里最常用的遍历+转换写法。Go 需要写循环：

```go
// Go
chunkTexts := make([]string, len(chunks))
for i, c := range chunks {
    chunkTexts[i] = c.text
}
```

```python
# Python — 一行
chunk_texts = [c["text"] for c in chunks]
```

---

## 7.8 端到端测试

```python
"""测试 RAG 完整链路"""
from rag.chunker import Chunker
from rag.embedder import Embedder
from rag.vector_db import VectorDB
from rag.retriever import Retriever
from rag.ingestion import ingest_documents

# 1. 准备假数据
text = """
对于过渡态计算，推荐使用 B3LYP 泛函配合 def2-SVP 基组。
在有机反应中，wB97XD 对色散作用的描述优于 B3LYP。
溶剂效应建议使用 SMD 模型。
HOMO-LUMO 能隙小于 0.5 eV 的体系需要多参考方法处理。
""" * 10  # 重复 10 次让文本足够长

with open("/tmp/test_knowledge.txt", "w") as f:
    f.write(text)

# 2. 建库
chunker = Chunker(chunk_size=200, overlap=30)
embedder = Embedder()  # 使用 fallback 假 embedding
vector_db = VectorDB()
retriever = Retriever(embedder, vector_db)

ingest_documents(["/tmp/test_knowledge.txt"], chunker, embedder, vector_db)
print(f"入库 chunk 数: {vector_db.count()}")

# 3. 检索
results = retriever.retrieve("过渡态计算用什么泛函？", top_k=3)
for r in results:
    print(f"  [{r['similarity']:.3f}] {r['text'][:80]}...")

# 4. 拼成 context
context = retriever.retrieve_as_context("溶剂效应怎么处理？")
print(f"\n拼接后的 context:\n{context}")
```

---

## 7.9 本课检查清单

- [ ] Chunker 能按 chunk_size 和 overlap 正确切分文本
- [ ] Embedder 能返回向量（哪怕是假 fallback 向量）
- [ ] VectorDB 能插入和搜索，搜索结果按相似度排序
- [ ] Retriever.retrieve_as_context() 返回可直接拼进 prompt 的文本
- [ ] 理解余弦相似度在检索中的作用
- [ ] 能解释 `zip`、列表推导式、`lambda` 各自做了什么

---

## 7.10 常见报错

| 报错 | 原因 | 解决 |
|------|------|------|
| `FileNotFoundError` on ingest | 文档路径写错了 | `ls` 确认文件存在 |
| `AttributeError: 'list' object has no attribute 'sort'` | 对 list 用了 `.sort()` 但写成 `list = list.sort()` | `.sort()` 就地排序返回 None |
| embedding 返回全是 0 | API key 或网络有问题 | 检查 fallback 是否触发 |
| search 结果全不相关 | chunk 太大了或 embedding 模型不好 | 调小 chunk_size，换更好的 embedding 模型 |

---

下一课：[第八课：RAG + Agent 融合](lesson-08-rag-agent.md)
