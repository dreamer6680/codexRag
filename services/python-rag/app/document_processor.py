"""Document normalization and deterministic text chunking."""
from pathlib import Path

from .document_structure import StructuredDocument
from .markdown_parser import MarkdownStructureParser
from .models import ChunkInput, Document, IndexRequest
from .structure_chunker import StructureAwareChunker


class DocumentProcessor:
    def __init__(self, chunk_size: int = 900, chunk_overlap: int = 120) -> None:
        if chunk_size <= 0 or not 0 <= chunk_overlap < chunk_size:
            raise ValueError("chunk_size must be positive and overlap smaller than it")
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.text_parser = MarkdownStructureParser()
        self.chunker = StructureAwareChunker(max_chars=chunk_size)

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
        structured = self.structure(document)
        chunks = self.chunker.chunk(structured)
        if not chunks:
            raise ValueError("document content is empty")
        return IndexRequest(
            document_id=document.document_id,
            document_name=document.name,
            version=document.version,
            chunks=chunks,
        )

    def structure(self, document: Document) -> StructuredDocument:
        return self.text_parser.parse(
            document.document_id,
            document.name,
            document.content,
            document.version,
        )
