"""Document normalization and deterministic text chunking."""
from pathlib import Path

from .models import ChunkInput, Document, IndexRequest


class DocumentProcessor:
    def __init__(self, chunk_size: int = 900, chunk_overlap: int = 120) -> None:
        if chunk_size <= 0 or not 0 <= chunk_overlap < chunk_size:
            raise ValueError("chunk_size must be positive and overlap smaller than it")
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def from_text(
        self, document_id: str, name: str, content: str, version: int = 1
    ) -> Document:
        return Document(
            document_id=document_id,
            name=name,
            content=content.strip(),
            version=version,
        )

    def from_file(self, path: str | Path, document_id: str, version: int = 1) -> Document:
        source = Path(path)
        if source.suffix.lower() not in {".txt", ".md"}:
            raise ValueError("Direct file loading supports .txt/.md; use MinerU for PDF/Office files")
        return self.from_text(document_id, source.name, source.read_text(encoding="utf-8"), version)

    def to_index_request(self, document: Document) -> IndexRequest:
        text = document.content
        chunks: list[ChunkInput] = []
        start = 0
        while start < len(text):
            end = min(len(text), start + self.chunk_size)
            chunks.append(
                ChunkInput(
                    text=text[start:end],
                    section=f"chars:{start}-{end}",
                    char_start=start,
                    char_end=end,
                )
            )
            if end == len(text):
                break
            start = end - self.chunk_overlap
        if not chunks:
            raise ValueError("document content is empty")
        return IndexRequest(
            document_id=document.document_id,
            document_name=document.name,
            version=document.version,
            chunks=chunks,
        )
