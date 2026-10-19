"""Run inside the backend image before activation; uses temporary data only."""
import os
from pathlib import Path
import tempfile


with tempfile.TemporaryDirectory(prefix='qap-storage-') as directory:
    os.environ['QAP_MILVUS_URI'] = str(Path(directory) / 'vectors.db')
    os.environ['EMBED_API_KEY'] = 'offline-smoke-test'
    from config.settings import settings
    from rag.vector_db import MilvusClient
    from memory.models import MemoryItem
    from memory.store import MilvusStore

    documents = MilvusClient()
    assert documents.available, 'RAG vector storage unavailable'
    vector = [1.0] + [0.0] * (settings.EMBED_DIM - 1)
    documents.insert([vector], [{'text': 'smoke', 'source': 'deployment', 'chunk_idx': 0}])
    assert documents.search(vector, 1)[0]['text'] == 'smoke'
    memories = MilvusStore()
    assert memories.available, 'Long-term memory storage unavailable'
    assert memories.add(MemoryItem(content='smoke', user_id='smoke', embedding=vector))
    rows = memories.client.query('agent_memories', filter='user_id == "smoke"', output_fields=['text'])
    assert rows[0]['text'] == 'smoke'
    documents.client.close()
    memories.client.close()
    print('PASS temporary RAG vector insert/search and long-term memory insert/query')
