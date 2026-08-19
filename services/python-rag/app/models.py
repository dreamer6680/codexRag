from datetime import datetime
from typing import Any, Literal
from uuid import UUID
from pydantic import BaseModel, Field, field_validator

from .document_structure import BoundingBox, ChunkEntities


class Citation(BaseModel):
    document_id: str
    document_name: str
    version: int
    page: int | None = None
    section: str | None = None
    excerpt: str
    confidence: float = Field(ge=0, le=1)
    chunk_index: int | None = None
    chunk_type: str | None = None
    entities: ChunkEntities = Field(default_factory=ChunkEntities)
    parser_confidence: float = Field(default=1, ge=0, le=1)
    dense_score: float | None = Field(default=None, ge=0, le=1)
    lexical_score: float | None = Field(default=None, ge=0)
    rrf_score: float | None = Field(default=None, ge=0)
    exact_entity_match: bool = False
    relation_coverage: bool = False
    retrieval_sources: list[str] = Field(default_factory=list)


class QueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    document_ids: list[str] = Field(default_factory=list)
    conversation_id: str | None = None
    strategy: Literal["vector", "mqe", "hyde", "hybrid"] | None = None


class QueryResponse(BaseModel):
    status: Literal["answered", "refused", "unavailable"]
    answer: str
    citations: list[Citation] = Field(default_factory=list)
    confidence: Literal["high", "medium", "low", "none"] = "none"
    model: str | None = None
    reason: str | None = None


class ChunkInput(BaseModel):
    text: str = Field(min_length=1)
    page: int | None = None
    section: str | None = None
    confidence: float = Field(default=1, ge=0, le=1)
    char_start: int | None = Field(default=None, ge=0)
    char_end: int | None = Field(default=None, ge=0)
    chunk_type: str = "paragraph"
    section_path: list[str] = Field(default_factory=list)
    parent_context: str | None = None
    keywords: list[str] = Field(default_factory=list)
    entities: ChunkEntities = Field(default_factory=ChunkEntities)
    bbox: BoundingBox | None = None
    parser_confidence: float = Field(default=1, ge=0, le=1)

    @field_validator("text")
    @classmethod
    def text_must_contain_non_whitespace(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("chunk text must not be blank")
        return value


class IndexRequest(BaseModel):
    owner_id: UUID | None = None
    document_id: str
    document_name: str
    version: int = Field(ge=1)
    chunks: list[ChunkInput] = Field(min_length=1)


class DocumentChunkDetail(BaseModel):
    index: int
    page: int | None = None
    section: str | None = None
    text: str
    char_start: int | None = None
    char_end: int | None = None
    confidence: float = Field(default=1, ge=0, le=1)
    chunk_type: str = "paragraph"
    section_path: list[str] = Field(default_factory=list)
    parent_context: str | None = None
    keywords: list[str] = Field(default_factory=list)
    entities: ChunkEntities = Field(default_factory=ChunkEntities)
    bbox: BoundingBox | None = None
    parser_confidence: float = Field(default=1, ge=0, le=1)


class StoredChunk(BaseModel):
    """Qdrant chunk payload normalized for non-vector retrieval."""

    document_id: str
    document_name: str
    version: int
    chunk_index: int
    text: str
    page: int | None = None
    section: str | None = None
    confidence: float = Field(default=1, ge=0, le=1)
    chunk_type: str = "paragraph"
    section_path: list[str] = Field(default_factory=list)
    parent_context: str | None = None
    keywords: list[str] = Field(default_factory=list)
    entities: ChunkEntities = Field(default_factory=ChunkEntities)
    bbox: BoundingBox | None = None
    parser_confidence: float = Field(default=1, ge=0, le=1)


class ServiceHealth(BaseModel):
    name: str
    healthy: bool
    detail: str | None = None


class UploadResponse(BaseModel):
    document_id: str
    document_name: str
    version: int
    indexed_chunks: int
    parser: str
    low_confidence_pages: list[int] = Field(default_factory=list)
    status: Literal["ready"] = "ready"


class RebuildDocumentResult(BaseModel):
    document_id: str
    document_name: str
    old_version: int
    new_version: int | None = None
    status: Literal["ready", "failed"]
    indexed_chunks: int = 0
    error: str | None = None


class RebuildResponse(BaseModel):
    results: list[RebuildDocumentResult]
    succeeded: int
    failed: int


class DocumentRecord(BaseModel):
    owner_id: UUID | None = None
    document_id: str
    document_name: str
    version: int
    content_type: str | None = None
    parser: str
    status: Literal["indexing", "ready", "index_failed"] = "ready"
    page_count: int | None = None
    pdf_type: str | None = None
    chunk_count: int
    original_object_key: str
    markdown_object_key: str
    created_at: str | None = None
    updated_at: str | None = None


class DocumentListResponse(BaseModel):
    documents: list[DocumentRecord]


class DocumentDetailResponse(DocumentRecord):
    original_url: str
    markdown: str
    chunks: list[DocumentChunkDetail]


class Document(BaseModel):
    """Normalized document exchanged by all processing/indexing stages."""

    document_id: str
    name: str
    content: str
    version: int = Field(default=1, ge=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ConversationSummary(BaseModel):
    id: UUID
    title: str
    created_at: datetime
    updated_at: datetime


class ChatMessage(BaseModel):
    id: UUID
    conversation_id: UUID
    role: Literal["user", "assistant"]
    content: str
    status: Literal["pending", "completed", "failed"]
    citations: list[Citation] = Field(default_factory=list)
    confidence: Literal["high", "medium", "low", "none"] = "none"
    error: str | None = None
    created_at: datetime


class ConversationDetail(ConversationSummary):
    summary: str = ""
    summarized_through_message_id: UUID | None = None
    selected_document_ids: list[str] = Field(default_factory=list)
    messages: list[ChatMessage] = Field(default_factory=list)


class ConversationListResponse(BaseModel):
    conversations: list[ConversationSummary]


class CreateConversationRequest(BaseModel):
    title: str | None = Field(default=None, max_length=120)


class UpdateConversationRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    document_ids: list[str] | None = None


class SendMessageRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)


class SendMessageResponse(BaseModel):
    conversation: ConversationSummary
    user_message: ChatMessage
    assistant_message: ChatMessage
