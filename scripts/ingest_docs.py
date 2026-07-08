from rag.chunker import Chunker
from rag.embedder import Embedder
from rag.vector_db import MilvusClient

chunker = Chunker()
embedder = Embedder()
vector_db = MilvusClient()

# TODO: implement document ingestion pipeline
