"""Normalized, source-aware document structure shared by every parser."""
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


BlockType = Literal["heading", "paragraph", "list_item", "table_row", "code", "other"]


def normalize_text(value: str) -> str:
    """Collapse layout whitespace without changing visible text order."""
    return " ".join(value.replace("\r", "\n").split())


def section_label(path: list[str]) -> str | None:
    parts = [normalize_text(part) for part in path if normalize_text(part)]
    return " / ".join(parts) or None


class BoundingBox(BaseModel):
    x0: float
    y0: float
    x1: float
    y1: float

    @model_validator(mode="after")
    def coordinates_are_ordered(self):
        if self.x1 < self.x0 or self.y1 < self.y0:
            raise ValueError("bounding box coordinates must be ordered")
        return self


class ChunkEntities(BaseModel):
    companies: list[str] = Field(default_factory=list)
    roles: list[str] = Field(default_factory=list)
    projects: list[str] = Field(default_factory=list)
    dates: list[str] = Field(default_factory=list)
    people: list[str] = Field(default_factory=list)


class DocumentBlock(BaseModel):
    block_type: BlockType
    text: str = Field(min_length=1)
    page: int | None = Field(default=None, ge=1)
    bbox: BoundingBox | None = None
    section_path: list[str] = Field(default_factory=list)
    char_start: int | None = Field(default=None, ge=0)
    char_end: int | None = Field(default=None, ge=0)
    parser_confidence: float = Field(default=1, ge=0, le=1)
    heading_level: int | None = Field(default=None, ge=1, le=6)
    list_level: int | None = Field(default=None, ge=0)

    @field_validator("text")
    @classmethod
    def normalize_block_text(cls, value: str) -> str:
        normalized = normalize_text(value)
        if not normalized:
            raise ValueError("block text must not be blank")
        return normalized

    @property
    def section(self) -> str | None:
        return section_label(self.section_path)


class StructuredDocument(BaseModel):
    document_id: str
    name: str
    blocks: list[DocumentBlock] = Field(min_length=1)
    markdown: str = ""
    parser: str = "structured-text"
    version: int = Field(default=1, ge=1)
