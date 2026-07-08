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
        embeddings = embedder.embed(chunks)
        metadata = [{"source": path, "chunk_idx": i} for i in range(len(chunks))]
        vector_db.insert(embeddings, metadata)
