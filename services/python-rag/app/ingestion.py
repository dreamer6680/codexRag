"""Document parsing, chunking and index rebuilding."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable
import httpx

from .document_processor import DocumentProcessor
from .document_structure import StructuredDocument
from .models import (
    DocumentRecord,
    IndexRequest,
    RebuildDocumentResult,
    RebuildResponse,
)
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
    """Parse documents, build structure and generate chunks."""

    def __init__(
        self,
        mineru_parser: MineruParser | None = None,
        processor: DocumentProcessor | None = None,
    ) -> None:
        self.mineru_parser = mineru_parser or self._parse_with_mineru
        self.processor = processor or DocumentProcessor()
        self.chunker = StructureAwareChunker(
            max_chars=self.processor.chunk_size
        )

    async def parse(
        self,
        document_id: str,
        filename: str,
        raw: bytes,
        content_type: str,
        version: int = 1,
    ) -> IngestionResult:

        suffix = Path(filename).suffix.lower()

        # PDF 统一交给 MinerU
        if suffix == ".pdf":
            structured = await self._parse_pdf(
                document_id,
                filename,
                raw,
                content_type,
                version,
            )

        # TXT / Markdown 直接读取
        else:
            try:
                content = raw.decode("utf-8-sig")
            except UnicodeDecodeError as exc:
                raise ValueError(
                    "TXT/Markdown 文件必须使用 UTF-8 编码"
                ) from exc

            document = self.processor.from_text(
                document_id,
                filename,
                content,
                version,
            )
            structured = self.processor.structure(document)

        # 统一进行结构化 Chunk
        chunks = self.chunker.chunk(structured)

        if not chunks:
            raise ValueError("document content is empty")

        request = IndexRequest(
            document_id=document_id,
            document_name=filename,
            version=version,
            chunks=chunks,
        )

        low_confidence_pages = sorted(
            {
                block.page
                for block in structured.blocks
                if block.page is not None
                and block.parser_confidence < 0.7
            }
        )

        return IngestionResult(
            structured=structured,
            request=request,
            parser=structured.parser,
            markdown=structured.markdown,
            low_confidence_pages=low_confidence_pages,
        )

    async def _parse_pdf(
        self,
        document_id: str,
        filename: str,
        raw: bytes,
        content_type: str,
        version: int,
    ) -> StructuredDocument:

        markdown = await self.mineru_parser(
            filename,
            raw,
            content_type,
        )

        document = self.processor.from_text(
            document_id,
            filename,
            markdown,
            version,
        )

        structured = self.processor.structure(document)

        return structured.model_copy(
            update={"parser": "mineru"},
        )

    async def _parse_with_mineru(
        self,
        filename: str,
        raw: bytes,
        content_type: str,
    ) -> str:

        async with httpx.AsyncClient(timeout=900) as client:
            response = await client.post(
                f"{settings.mineru_url.rstrip('/')}/parse",
                files={
                    "file": (
                        filename,
                        raw,
                        content_type,
                    )
                },
            )

            response.raise_for_status()
            payload = response.json()

        markdown = payload.get("markdown")

        if not isinstance(markdown, str) or not markdown.strip():
            raise ValueError("MinerU 返回内容为空")

        return markdown


class IndexRebuilder:
    """Rebuild document indexes and publish a new version."""

    def __init__(
        self,
        catalog=None,
        storage=None,
        store=None,
        ingestion=None,
    ) -> None:

        if catalog is None:
            from .document_catalog import DocumentCatalog

            catalog = DocumentCatalog()

        if storage is None:
            from .object_storage import ObjectStorage

            storage = ObjectStorage()

        if store is None:
            from .vector_store import VectorStore

            store = VectorStore()

        self.catalog = catalog
        self.storage = storage
        self.store = store
        self.ingestion = ingestion or IngestionService()

    async def rebuild_all(self, owner_id) -> RebuildResponse:
        results = []

        for record in self.catalog.list_documents(owner_id):
            results.append(
                await self._rebuild_document(owner_id, record)
            )

        succeeded = sum(
            result.status == "ready"
            for result in results
        )

        return RebuildResponse(
            results=results,
            succeeded=succeeded,
            failed=len(results) - succeeded,
        )

    async def _rebuild_document(
        self,
        owner_id,
        record: DocumentRecord,
    ) -> RebuildDocumentResult:

        new_version = record.version + 1
        reserved = False
        indexed = False

        try:
            # 1. 从 MinIO 取回原始文件
            raw = self.storage.get_bytes(
                record.original_object_key
            )

            # 2. 重新解析
            parsed = await self.ingestion.parse(
                record.document_id,
                record.document_name,
                raw,
                record.content_type or "application/octet-stream",
                version=new_version,
            )

            # 3. 预留新版本
            reserved = self.catalog.reserve_index_version(
                owner_id,
                record.document_id,
                record.document_name,
                new_version,
            )

            if not reserved:
                raise RuntimeError("无法预留新的索引版本")

            # 4. 建立新的向量索引
            request = parsed.request.model_copy(
                update={"owner_id": owner_id}
            )

            count = await self.store.index(request)
            indexed = True

            # 5. 保存新的 Markdown
            markdown_key = (
                f"users/{owner_id}/documents/"
                f"{record.document_id}/v{new_version}/parsed.md"
            )

            self.storage.put_bytes(
                markdown_key,
                parsed.markdown.encode("utf-8"),
                "text/markdown; charset=utf-8",
            )

            # 6. 发布新版本
            new_record = record.model_copy(
                update={
                    "version": new_version,
                    "parser": parsed.parser,
                    "status": "ready",
                    "chunk_count": count,
                    "markdown_object_key": markdown_key,
                }
            )

            if not self.catalog.finalize_index(
                new_record,
                owner_id,
            ):
                raise RuntimeError("新索引版本发布失败")

        except Exception as exc:

            # 新版本已经预留，则标记失败
            if reserved:
                self.catalog.mark_index_failed(
                    owner_id,
                    record.document_id,
                    new_version,
                )

            # 新版本已经写入向量库，则删除
            if indexed:
                try:
                    self.store.delete_document_version(
                        owner_id,
                        record.document_id,
                        new_version,
                    )
                except Exception:
                    pass

            return RebuildDocumentResult(
                document_id=record.document_id,
                document_name=record.document_name,
                old_version=record.version,
                new_version=new_version,
                status="failed",
                error=str(exc),
            )

        # 7. 新版本发布成功后删除旧向量
        try:
            self.store.delete_document_version(
                owner_id,
                record.document_id,
                record.version,
            )
        except Exception:
            # 新版本已经生效，旧数据可以以后清理
            pass

        return RebuildDocumentResult(
            document_id=record.document_id,
            document_name=record.document_name,
            old_version=record.version,
            new_version=new_version,
            status="ready",
            indexed_chunks=count,
        )
