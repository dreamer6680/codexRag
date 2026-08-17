from typing import Any, Literal
from pydantic import BaseModel, Field, field_validator


class Citation(BaseModel):
    document_id: str
    document_name: str
    version: int
    page: int | None = None
    section: str | None = None
    excerpt: str
    confidence: float = Field(ge=0, le=1)


class QueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    document_ids: list[str] = []
    conversation_id: str | None = None
    strategy: Literal["vector", "mqe", "hyde", "hybrid"] | None = None


class QueryResponse(BaseModel):
    status: Literal["answered", "refused", "unavailable"]
    answer: str
    citations: list[Citation] = []
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

    @field_validator("text")
    @classmethod
    def text_must_contain_non_whitespace(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("chunk text must not be blank")
        return value


class IndexRequest(BaseModel):
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
    status: Literal["ready"] = "ready"


class DocumentRecord(BaseModel):
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
