class Chunker:
    """文本切片：把长文档切成可被 embedding 模型处理的小块"""

    def __init__(self, chunk_size: int = 512, overlap: int = 50):
        self.chunk_size = chunk_size
        self.overlap = overlap

    def chunk(self, text: str) -> list[dict]:
        """切分文本，返回 [{text, index, start, end}, ...]"""
        # 文本太短，不需要切
        if len(text) <= self.chunk_size:
            return [{
                "text": text,
                "index": 0,
                "start": 0,
                "end": len(text),
            }]

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
            # 前进的步长 = chunk_size - overlap（有重叠，避免关键句被切断）
            start += self.chunk_size - self.overlap
        return chunks
