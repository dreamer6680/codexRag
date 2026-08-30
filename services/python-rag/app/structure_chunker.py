"""Structure-aware chunk creation."""

from __future__ import annotations

import re

from .document_structure import (
    BoundingBox,
    ChunkEntities,
    DocumentBlock,
    StructuredDocument,
    section_label,
)
from .models import ChunkInput


LATIN_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_.+-]{1,}")


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _keywords(text: str) -> list[str]:
    return _unique(LATIN_TOKEN_RE.findall(text))


class StructureAwareChunker:

    def __init__(self, max_chars: int = 900,overlap: int = 120) -> None:
        if max_chars <= 0:
            raise ValueError("max_chars must be positive")

        self.max_chars = max_chars
        self.overlap = overlap

    def chunk(self, document: StructuredDocument) -> list[ChunkInput]:
        chunks: list[ChunkInput] = []

        for block in document.blocks:
            chunks.append(
                ChunkInput(
                    text=block.text,
                    page=block.page,
                    section=block.section,
                    confidence=block.parser_confidence,
                    char_start=block.char_start,
                    char_end=block.char_end,
                    chunk_type=block.block_type,
                    section_path=block.section_path,
                    parent_context=section_label(block.section_path),
                    keywords=_keywords(block.text),
                    entities=ChunkEntities(),
                    bbox=block.bbox,
                    parser_confidence=block.parser_confidence,
                )
            )

        if not chunks:
            headings = [
                block
                for block in document.blocks
                if block.block_type == "heading"
            ]

            if headings:
                block = headings[-1]

                chunks.append(
                    ChunkInput(
                        text=block.text,
                        page=block.page,
                        section=block.section,
                        chunk_type="heading",
                        section_path=block.section_path,
                        parent_context=section_label(block.section_path),
                        bbox=block.bbox,
                        parser_confidence=block.parser_confidence,
                    )
                )

        return chunks