import asyncio
import sys
from uuid import uuid4
from pathlib import Path

import httpx
import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import Response

# Support both `python main.py` from this folder and `uvicorn app.main:app`
# from the python-rag service root.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from app.graph import run_query
    from app.document_processor import DocumentProcessor
    from app.document_catalog import DocumentCatalog
    from app.models import DocumentDetailResponse, DocumentListResponse, DocumentRecord, IndexRequest, QueryRequest, QueryResponse, ServiceHealth, UploadResponse
    from app.object_storage import ObjectStorage
    from app.vector_store import VectorStore
    from app.ollama import OllamaClient
    from app.settings import settings
else:
    from .graph import run_query
    from .document_processor import DocumentProcessor
    from .document_catalog import DocumentCatalog
    from .models import DocumentDetailResponse, DocumentListResponse, DocumentRecord, IndexRequest, QueryRequest, QueryResponse, ServiceHealth, UploadResponse
    from .object_storage import ObjectStorage
    from .vector_store import VectorStore
    from .ollama import OllamaClient
    from .settings import settings

app = FastAPI(title="Local RAG AI service", version="0.1.0")
object_storage = ObjectStorage()
document_catalog = DocumentCatalog()


@app.get("/health", response_model=list[ServiceHealth])
async def health():
    async def check(name: str, url: str) -> ServiceHealth:
        try:
            async with httpx.AsyncClient(timeout=3) as client:
                await client.get(url)
            return ServiceHealth(name=name, healthy=True)
        except httpx.HTTPError as exc:
            return ServiceHealth(name=name, healthy=False, detail=str(exc))
    ollama = OllamaClient()
    model, detail = await ollama.choose_chat_model()
    checks = await asyncio.gather(check("qdrant", f"{settings.qdrant_url}/healthz"), check("mineru", f"{settings.mineru_url}/health"))
    checks.insert(0, ServiceHealth(name="ollama", healthy=model is not None, detail=detail))
    return checks


@app.post("/rag/query", response_model=QueryResponse)
async def query(payload: QueryRequest):
    try:
        document_scope = document_catalog.ready_document_scopes()
    except Exception:
        return QueryResponse(
            status="unavailable",
            answer="文档目录当前不可用。",
            confidence="none",
            reason="catalog_unavailable",
        )
    if payload.document_ids:
        requested = set(payload.document_ids)
        document_scope = [scope for scope in document_scope if scope[0] in requested]
    return await run_query(payload.question, document_scope, payload.strategy)


@app.post("/rag/index")
async def index(payload: IndexRequest):
    count = await VectorStore().index(payload)
    content = "\n\n".join(chunk.text for chunk in payload.chunks)
    original_key = f"documents/{payload.document_id}/v{payload.version}/original/{payload.document_name}"
    markdown_key = f"documents/{payload.document_id}/v{payload.version}/parsed.md"
    object_storage.put_bytes(original_key, content.encode("utf-8"), "text/markdown; charset=utf-8")
    object_storage.put_bytes(markdown_key, content.encode("utf-8"), "text/markdown; charset=utf-8")
    pages = {chunk.page for chunk in payload.chunks if chunk.page is not None}
    document_catalog.upsert(
        DocumentRecord(
            document_id=payload.document_id,
            document_name=payload.document_name,
            version=payload.version,
            content_type="text/markdown",
            parser="api-index",
            page_count=len(pages) or None,
            chunk_count=count,
            original_object_key=original_key,
            markdown_object_key=markdown_key,
        )
    )
    return {"document_id": payload.document_id, "version": payload.version, "indexed_chunks": count}


@app.post("/rag/upload", response_model=UploadResponse)
async def upload(
    file: UploadFile = File(...),
    extracted_markdown: str | None = Form(default=None),
    parser: str | None = Form(default=None),
    page_count: int | None = Form(default=None),
    pdf_type: str | None = Form(default=None),
):
    """Parse, chunk, embed and index one user-uploaded document."""
    filename = Path(file.filename or "").name
    suffix = Path(filename).suffix.lower()
    if not filename or suffix not in {".pdf", ".txt", ".md"}:
        raise HTTPException(415, "当前仅支持 PDF、TXT 和 Markdown 文件")

    raw = await file.read()
    if not raw:
        raise HTTPException(400, "上传文件为空")
    if len(raw) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(413, f"文件不能超过 {settings.max_upload_mb} MB")

    parser_used = "plain-text"
    if suffix == ".pdf" and extracted_markdown and extracted_markdown.strip():
        content = extracted_markdown
        parser_used = parser or "pdf-inspector"
    elif suffix == ".pdf":
        try:
            async with httpx.AsyncClient(timeout=900) as client:
                response = await client.post(
                    f"{settings.mineru_url.rstrip('/')}/parse",
                    files={"file": (filename, raw, file.content_type or "application/pdf")},
                )
                response.raise_for_status()
                content = response.json()["markdown"]
                parser_used = "mineru"
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[-1000:]
            raise HTTPException(422, f"MinerU 解析失败：{detail}") from exc
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            raise HTTPException(503, f"MinerU 服务不可用或返回无效结果：{exc}") from exc
    else:
        try:
            content = raw.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise HTTPException(415, "TXT/Markdown 文件必须使用 UTF-8 编码") from exc

    document_id = str(uuid4())
    version = 1
    original_key = f"documents/{document_id}/v{version}/original/{filename}"
    markdown_key = f"documents/{document_id}/v{version}/parsed.md"
    processor = DocumentProcessor()
    document = processor.from_text(document_id, filename, content)
    request = processor.to_index_request(document)
    try:
        object_storage.put_bytes(original_key, raw, file.content_type or "application/octet-stream")
        object_storage.put_bytes(markdown_key, content.encode("utf-8"), "text/markdown; charset=utf-8")
        count = await VectorStore().index(request)
    except Exception as exc:
        raise HTTPException(503, f"向量索引失败，请检查 Ollama 和 Qdrant：{exc}") from exc
    document_catalog.upsert(
        DocumentRecord(
            document_id=document_id,
            document_name=filename,
            version=version,
            content_type=file.content_type or "application/octet-stream",
            parser=parser_used,
            page_count=page_count,
            pdf_type=pdf_type,
            chunk_count=count,
            original_object_key=original_key,
            markdown_object_key=markdown_key,
        )
    )
    return UploadResponse(
        document_id=document_id,
        document_name=filename,
        version=version,
        indexed_chunks=count,
        parser=parser_used,
    )


@app.get("/rag/documents", response_model=DocumentListResponse)
async def documents():
    return DocumentListResponse(documents=document_catalog.list_documents())


@app.get("/rag/documents/{document_id}", response_model=DocumentDetailResponse)
async def document_detail(document_id: str):
    record = document_catalog.get(document_id)
    if not record:
        raise HTTPException(404, "Document not found")
    markdown = object_storage.get_bytes(record.markdown_object_key).decode("utf-8")
    chunks = VectorStore().chunks_for_document(document_id, record.version)
    return DocumentDetailResponse(
        **record.model_dump(),
        original_url=f"/rag/documents/{document_id}/original",
        markdown=markdown,
        chunks=chunks,
    )


@app.get("/rag/documents/{document_id}/original")
async def document_original(document_id: str):
    record = document_catalog.get(document_id)
    if not record:
        raise HTTPException(404, "Document not found")
    data, content_type = object_storage.stream(record.original_object_key)
    return Response(content=data, media_type=content_type)


if __name__ == "__main__":
    uvicorn.run(app, host=settings.rag_host, port=settings.rag_port)
