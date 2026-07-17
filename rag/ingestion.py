from rag.chunker import Chunker
from rag.embedder import Embedder
from rag.vector_db import MilvusClient


def ingest_documents(file_paths: list[str], chunker: Chunker,
                     embedder: Embedder, vector_db: MilvusClient):
    """Ingest documents into the vector database."""
    for path in file_paths:
        with open(path) as f:
            text = f.read()
        chunks = chunker.chunk(text)
        # embed 要 list[str]，Chunker 返回的是 list[dict]，需取出 "text"
        chunk_texts = [c["text"] for c in chunks]
        embeddings = embedder.embed(chunk_texts)
        # metadata 必须带 "text"，否则搜索时拿不到原文
        metadata = [
            {"text": chunks[i]["text"], "source": path, "chunk_idx": i}
            for i in range(len(chunks))
        ]
        vector_db.insert(embeddings, metadata)
