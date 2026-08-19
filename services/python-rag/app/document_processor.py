"""Document normalization and deterministic text chunking."""
from pathlib import Path

from .document_structure import StructuredDocument
from .markdown_parser import MarkdownStructureParser
from .models import ChunkInput, Document, IndexRequest


class DocumentProcessor:
    def __init__(self, chunk_size: int = 900, chunk_overlap: int = 120) -> None:
        if chunk_size <= 0 or not 0 <= chunk_overlap < chunk_size:
            raise ValueError("chunk_size must be positive and overlap smaller than it")
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.text_parser = MarkdownStructureParser()

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
        content_blocks = [block for block in structured.blocks if block.block_type != "heading"]
        if not content_blocks:
            content_blocks = structured.blocks
        chunks = [
            ChunkInput(
                text=block.text,
                page=block.page,
                section=block.section,
                char_start=block.char_start,
                char_end=block.char_end,
                chunk_type=block.block_type,
                section_path=block.section_path,
                bbox=block.bbox,
                parser_confidence=block.parser_confidence,
            )
            for block in content_blocks
        ]
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
