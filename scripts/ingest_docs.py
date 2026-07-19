import sys
from rag.chunker import Chunker
from rag.embedder import Embedder
from rag.vector_db import MilvusClient
from rag.ingestion import ingest_documents

chunker = Chunker(chunk_size=512, overlap=50)
embedder = Embedder()
vector_db = MilvusClient()

# 将要入库的文件路径写在下面，或从命令行传入
file_paths = sys.argv[1:] if len(sys.argv) > 1 else [
    "data/quantum_basics.txt",
    "data/test_dft.pdf",
]

ingest_documents(file_paths, chunker, embedder, vector_db)
print("全部入库完成")
