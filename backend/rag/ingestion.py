from PyPDF2 import PdfReader
from docx import Document as DocxDocument
from rag.chunker import Chunker
from rag.embedder import Embedder
from rag.vector_db import MilvusClient


def extract_pdf_text(path: str) -> str:
    """从 PDF 提取纯文本"""
    reader = PdfReader(path)
    pages = []
    for page in reader.pages:
        page_text = page.extract_text()
        if page_text:
            pages.append(page_text)
    return "\n".join(pages)


def extract_docx_text(path: str) -> str:
    """从 Word 文档提取纯文本"""
    doc = DocxDocument(path)
    paragraphs = []
    for para in doc.paragraphs:
        if para.text.strip():
            paragraphs.append(para.text)
    return "\n".join(paragraphs)


def read_file(path: str) -> str:
    """根据后缀读文件：PDF / DOCX / TXT"""
    if path.lower().endswith(".pdf"):
        return extract_pdf_text(path)
    elif path.lower().endswith(".docx"):
        return extract_docx_text(path)
    else:
        with open(path, encoding="utf-8") as f:
            return f.read()


def ingest_documents(file_paths: list[str], chunker: Chunker,
                     embedder: Embedder, vector_db: MilvusClient):
    """
    将文档入库：读文件 → 切片 → 向量化 → 写入 Milvus
    支持 .txt 和 .pdf
    """
    for path in file_paths:
        text = read_file(path)
        if not text.strip():
            print(f"[ingest] 警告: {path} 提取内容为空，跳过")
            continue

        chunks = chunker.chunk(text)
        chunk_texts = [c["text"] for c in chunks]
        embeddings = embedder.embed(chunk_texts)
        metadata = [
            {"text": chunks[i]["text"], "source": path, "chunk_idx": i}
            for i in range(len(chunks))
        ]
        vector_db.insert(embeddings, metadata)
        print(f"[ingest] {path}: {len(chunks)} 块入库完成")
