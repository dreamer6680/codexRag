"""Raw-file parsing and structure-aware chunk orchestration."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable

import httpx

from .document_processor import DocumentProcessor
from .document_structure import StructuredDocument
from .layout_parser import PdfLayoutParser
from .models import IndexRequest
from .settings import settings
from .structure_chunker import StructureAwareChunker


MineruParser = Callable[[str, bytes, str], Awaitable[str]]


@dataclass(frozen=True)
class IngestionResult:
    structured: StructuredDocument
    request: IndexRequest
    parser: str
    markdown: str
    low_confidence_pages: list[int]


class IngestionService:
    def __init__(
        self,
        layout_parser: PdfLayoutParser | None = None,
        mineru_parser: MineruParser | None = None,
        processor: DocumentProcessor | None = None,
    ) -> None:
        self.layout_parser = layout_parser or PdfLayoutParser()
        self.mineru_parser = mineru_parser or self._parse_with_mineru
        self.processor = processor or DocumentProcessor()
        self.chunker = StructureAwareChunker(max_chars=self.processor.chunk_size)

    async def parse(
        self,
        document_id: str,
        filename: str,
        raw: bytes,
        content_type: str,
        pdf_type: str | None = None,
        version: int = 1,
    ) -> IngestionResult:
        suffix = Path(filename).suffix.lower()
        if suffix == ".pdf":
            structured = await self._parse_pdf(
                document_id, filename, raw, content_type, pdf_type, version
            )
        else:
            try:
                content = raw.decode("utf-8-sig")
            except UnicodeDecodeError as exc:
                raise ValueError("TXT/Markdown 文件必须使用 UTF-8 编码") from exc
            document = self.processor.from_text(document_id, filename, content, version)
            structured = self.processor.structure(document)

        chunks = self.chunker.chunk(structured)
        if not chunks:
            raise ValueError("document content is empty")
        request = IndexRequest(
            document_id=document_id,
            document_name=filename,
            version=version,
            chunks=chunks,
        )
        low_pages = sorted(
            {
                block.page
                for block in structured.blocks
                if block.page is not None and block.parser_confidence < 0.7
            }
        )
        return IngestionResult(
            structured=structured,
            request=request,
            parser=structured.parser,
            markdown=structured.markdown,
            low_confidence_pages=low_pages,
        )

    async def _parse_pdf(
        self,
        document_id: str,
        filename: str,
        raw: bytes,
        content_type: str,
        pdf_type: str | None,
        version: int,
    ) -> StructuredDocument:
        layout_error: Exception | None = None
        if pdf_type not in {"Scanned", "ImageBased"}:
            try:
                return self.layout_parser.parse(document_id, filename, raw, version)
            except Exception as exc:
                layout_error = exc
                if pdf_type == "TextBased":
                    raise ValueError(f"PDF 布局解析失败：{exc}") from exc

        try:
            markdown = await self.mineru_parser(filename, raw, content_type)
        except Exception as exc:
            detail = f"；布局解析也失败：{layout_error}" if layout_error else ""
            raise RuntimeError(f"MinerU 解析失败：{exc}{detail}") from exc
        document = self.processor.from_text(document_id, filename, markdown, version)
        structured = self.processor.structure(document)
        return structured.model_copy(update={"parser": "mineru-structure"})

    async def _parse_with_mineru(self, filename: str, raw: bytes, content_type: str) -> str:
        async with httpx.AsyncClient(timeout=900) as client:
            response = await client.post(
                f"{settings.mineru_url.rstrip('/')}/parse",
                files={"file": (filename, raw, content_type)},
            )
            response.raise_for_status()
            payload = response.json()
        markdown = payload.get("markdown")
        if not isinstance(markdown, str) or not markdown.strip():
            raise ValueError("MinerU 返回内容为空")
        return markdown

