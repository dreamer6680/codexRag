import asyncio
import sys
from uuid import uuid4
from uuid import UUID
from pathlib import Path

import httpx
import uvicorn
from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse, Response

# Support both `python main.py` from this folder and `uvicorn app.main:app`
# from the python-rag service root.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from app.graph import run_query
    from app.ingestion import IndexRebuilder, IngestionService
    from app.document_catalog import DocumentCatalog
    from app.document_deletion import DocumentDeletionService, DocumentNotFound, DocumentPurgePending
    from app.models import DocumentDeleteResponse, DocumentDetailResponse, DocumentListResponse, DocumentRecord, IndexRequest, QueryRequest, QueryResponse, RebuildResponse, ServiceHealth, UploadResponse
    from app.object_storage import ObjectStorage
    from app.vector_store import VectorStore
    from app.ollama import OllamaClient
    from app.settings import settings
    from app.auth import AuthenticatedUser, require_user
    from app.chat_catalog import ChatCatalog
    from app.chat_context import ChatContextBuilder
    from app.models import ConversationDetail, ConversationListResponse, ConversationSummary, CreateConversationRequest, SendMessageRequest, SendMessageResponse, UpdateConversationRequest
else:
    from .graph import run_query
    from .ingestion import IndexRebuilder, IngestionService
    from .document_catalog import DocumentCatalog
    from .document_deletion import DocumentDeletionService, DocumentNotFound, DocumentPurgePending
    from .models import DocumentDeleteResponse, DocumentDetailResponse, DocumentListResponse, DocumentRecord, IndexRequest, QueryRequest, QueryResponse, RebuildResponse, ServiceHealth, UploadResponse
    from .object_storage import ObjectStorage
    from .vector_store import VectorStore
    from .ollama import OllamaClient
    from .settings import settings
    from .auth import AuthenticatedUser, require_user
    from .chat_catalog import ChatCatalog
    from .chat_context import ChatContextBuilder
    from .models import ConversationDetail, ConversationListResponse, ConversationSummary, CreateConversationRequest, SendMessageRequest, SendMessageResponse, UpdateConversationRequest

app = FastAPI(title="Local RAG AI service", version="0.1.0")
object_storage = ObjectStorage()
document_catalog = DocumentCatalog()
chat_catalog = ChatCatalog()
document_deletion = DocumentDeletionService(
    catalog=document_catalog,
    objects=object_storage,
)
EVIDENCE_REFUSAL = "现有知识库中没有足以支持该问题的可靠证据，因此我不能确认答案。"


def live_citations(owner_id: UUID, citations):
    if not citations:
        return []
    live_ids = document_catalog.live_document_ids(
        owner_id,
        list(dict.fromkeys(item.document_id for item in citations)),
    )
    return [item for item in citations if item.document_id in live_ids]


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
async def query(payload: QueryRequest, user: AuthenticatedUser = Depends(require_user)):
    try:
        document_catalog.upsert_user(user)
        document_catalog.ready_document_scopes(user.id, payload.document_ids)
        missing_document = any(
            not document_catalog.get(document_id, user.id)
            for document_id in payload.document_ids
        )
    except Exception:
        return QueryResponse(
            status="unavailable",
            answer="文档目录当前不可用。",
            confidence="none",
            reason="catalog_unavailable",
        )
    if missing_document:
        raise HTTPException(404, "Document not found")
    return await run_query(payload.question, user.id, payload.document_ids, payload.strategy)


@app.post("/rag/index")
async def index(payload: IndexRequest, user: AuthenticatedUser = Depends(require_user)):
    document_catalog.upsert_user(user)
    payload = payload.model_copy(update={"owner_id": user.id})
    reserved = document_catalog.reserve_index_version(
        user.id, payload.document_id, payload.document_name, payload.version
    )
    if not reserved:
        raise HTTPException(409, "文档版本必须严格递增")
    try:
        count = await VectorStore().index(payload)
        content = "\n\n".join(chunk.text for chunk in payload.chunks)
        original_key = f"users/{user.id}/documents/{payload.document_id}/v{payload.version}/original/{payload.document_name}"
        markdown_key = f"users/{user.id}/documents/{payload.document_id}/v{payload.version}/parsed.md"
        object_storage.put_bytes(original_key, content.encode("utf-8"), "text/markdown; charset=utf-8")
        object_storage.put_bytes(markdown_key, content.encode("utf-8"), "text/markdown; charset=utf-8")
        pages = {chunk.page for chunk in payload.chunks if chunk.page is not None}
        record = DocumentRecord(
            owner_id=user.id,
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
        if not document_catalog.finalize_index(record, user.id):
            raise HTTPException(409, "文档版本已被更新的索引请求取代")
    except Exception:
        document_catalog.mark_index_failed(user.id, payload.document_id, payload.version)
        raise
    return {"document_id": payload.document_id, "version": payload.version, "indexed_chunks": count}


@app.post("/rag/upload", response_model=UploadResponse)
async def upload(
    file: UploadFile = File(...),
    page_count: int | None = Form(default=None),
    pdf_type: str | None = Form(default=None),
    user: AuthenticatedUser = Depends(require_user),
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

    document_id = str(uuid4())
    version = 1
    document_catalog.upsert_user(user)
    original_key = f"users/{user.id}/documents/{document_id}/v{version}/original/{filename}"
    markdown_key = f"users/{user.id}/documents/{document_id}/v{version}/parsed.md"
    try:
        ingestion = await IngestionService().parse(
            document_id,
            filename,
            raw,
            file.content_type or "application/octet-stream",
            pdf_type=pdf_type,
            version=version,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except (RuntimeError, httpx.HTTPError) as exc:
        raise HTTPException(503, str(exc)) from exc
    content = ingestion.markdown
    parser_used = ingestion.parser
    request = ingestion.request.model_copy(update={"owner_id": user.id})
    try:
        object_storage.put_bytes(original_key, raw, file.content_type or "application/octet-stream")
        object_storage.put_bytes(markdown_key, content.encode("utf-8"), "text/markdown; charset=utf-8")
        count = await VectorStore().index(request)
    except Exception as exc:
        raise HTTPException(503, f"向量索引失败，请检查 Ollama 和 Qdrant：{exc}") from exc
    document_catalog.upsert(
        DocumentRecord(
            owner_id=user.id,
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
        ),
        user.id,
    )
    return UploadResponse(
        document_id=document_id,
        document_name=filename,
        version=version,
        indexed_chunks=count,
        parser=parser_used,
        low_confidence_pages=ingestion.low_confidence_pages,
    )


@app.get("/rag/documents", response_model=DocumentListResponse)
async def documents(user: AuthenticatedUser = Depends(require_user)):
    document_catalog.upsert_user(user)
    return DocumentListResponse(documents=document_catalog.list_documents(user.id))


@app.post("/rag/documents/rebuild", response_model=RebuildResponse)
async def rebuild_documents(user: AuthenticatedUser = Depends(require_user)):
    document_catalog.upsert_user(user)
    return await IndexRebuilder(
        catalog=document_catalog,
        storage=object_storage,
        store=VectorStore(),
        ingestion=IngestionService(),
    ).rebuild_all(user.id)


@app.delete("/rag/documents/{document_id}", response_model=DocumentDeleteResponse)
async def delete_document(document_id: str, user: AuthenticatedUser = Depends(require_user)):
    try:
        return document_deletion.delete(user.id, document_id)
    except DocumentNotFound as exc:
        raise HTTPException(404, "Document not found") from exc
    except DocumentPurgePending as exc:
        return JSONResponse(status_code=503, content=exc.result.model_dump())


@app.get("/rag/documents/{document_id}", response_model=DocumentDetailResponse)
async def document_detail(document_id: str, user: AuthenticatedUser = Depends(require_user)):
    record = document_catalog.get(document_id, user.id)
    if not record:
        raise HTTPException(404, "Document not found")
    markdown = object_storage.get_bytes(record.markdown_object_key).decode("utf-8")
    chunks = VectorStore().chunks_for_document(document_id, user.id, record.version)
    return DocumentDetailResponse(
        **record.model_dump(),
        original_url=f"/rag/documents/{document_id}/original",
        markdown=markdown,
        chunks=chunks,
    )


@app.get("/rag/documents/{document_id}/original")
async def document_original(document_id: str, user: AuthenticatedUser = Depends(require_user)):
    record = document_catalog.get(document_id, user.id)
    if not record:
        raise HTTPException(404, "Document not found")
    data, content_type = object_storage.stream(record.original_object_key)
    return Response(content=data, media_type=content_type)


@app.get("/rag/conversations", response_model=ConversationListResponse)
async def conversations(user: AuthenticatedUser = Depends(require_user)):
    chat_catalog.upsert_user(user)
    return ConversationListResponse(conversations=chat_catalog.list_conversations(user.id))


@app.post("/rag/conversations", response_model=ConversationSummary, status_code=201)
async def create_conversation(payload: CreateConversationRequest, user: AuthenticatedUser = Depends(require_user)):
    chat_catalog.upsert_user(user)
    return chat_catalog.create_conversation(user.id, payload.title)


@app.get("/rag/conversations/{conversation_id}", response_model=ConversationDetail)
async def conversation_detail(conversation_id: UUID, user: AuthenticatedUser = Depends(require_user)):
    conversation = chat_catalog.get_conversation(conversation_id, user.id)
    if not conversation:
        raise HTTPException(404, "Conversation not found")
    return conversation


@app.patch("/rag/conversations/{conversation_id}", response_model=ConversationDetail)
async def update_conversation(
    conversation_id: UUID,
    payload: UpdateConversationRequest,
    user: AuthenticatedUser = Depends(require_user),
):
    try:
        conversation = chat_catalog.update_conversation(
            conversation_id,
            user.id,
            payload.title,
            payload.document_ids,
        )
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    if not conversation:
        raise HTTPException(404, "Conversation not found")
    return conversation


@app.post("/rag/conversations/{conversation_id}/messages", response_model=SendMessageResponse)
async def send_message(
    conversation_id: UUID,
    payload: SendMessageRequest,
    user: AuthenticatedUser = Depends(require_user),
):
    before = chat_catalog.get_conversation(conversation_id, user.id)
    if not before:
        raise HTTPException(404, "Conversation not found")
    context = ChatContextBuilder(max_chars=max(1000, settings.context_max_chars // 5)).build(
        before.summary,
        before.messages,
        payload.question,
        before.summarized_through_message_id,
    )
    started = chat_catalog.start_turn(conversation_id, user.id, payload.question.strip())
    if not started:
        raise HTTPException(404, "Conversation not found")
    conversation, user_message, pending_assistant = started
    try:
        result = await run_query(
            payload.question.strip(),
            user.id,
            before.selected_document_ids,
            retrieval_query=context.retrieval_query,
            prompt_history=context.prompt_history,
        )
        if result.status == "unavailable":
            assistant_message = chat_catalog.fail_turn(
                pending_assistant.id,
                user.id,
                result.answer,
            )
        else:
            citations = live_citations(user.id, result.citations)
            answer = result.answer
            confidence = result.confidence
            if result.status == "answered" and result.citations and not citations:
                answer = EVIDENCE_REFUSAL
                confidence = "none"
            assistant_message = chat_catalog.finish_turn(
                pending_assistant.id,
                user.id,
                answer,
                citations,
                confidence,
            )
        if context.messages_to_summarize:
            transcript = "\n".join(
                f"{'用户' if item.role == 'user' else '助手'}：{item.content}"
                for item in context.messages_to_summarize
            )
            try:
                summary = await OllamaClient().summarize_conversation(before.summary, transcript)
                if summary:
                    chat_catalog.update_summary(
                        conversation_id,
                        user.id,
                        summary,
                        context.messages_to_summarize[-1].id,
                    )
            except Exception:
                pass
    except Exception as exc:
        assistant_message = chat_catalog.fail_turn(
            pending_assistant.id,
            user.id,
            "回答生成失败，请稍后重试",
        )
    return SendMessageResponse(
        conversation=conversation,
        user_message=user_message,
        assistant_message=assistant_message,
    )


if __name__ == "__main__":
    uvicorn.run(app, host=settings.rag_host, port=settings.rag_port)
