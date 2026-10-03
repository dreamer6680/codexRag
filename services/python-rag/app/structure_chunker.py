"""Hierarchical, structure-aware chunk creation with context enrichment."""

from __future__ import annotations

import re
from dataclasses import dataclass
from uuid import NAMESPACE_URL, uuid5

from .document_structure import (
    BoundingBox,
    ChunkEntities,
    DocumentBlock,
    StructuredDocument,
    section_label,
)
from .models import ChunkInput


LATIN_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_.+-]{1,}")
SENTENCE_RE = re.compile(r"(?<=[。！？.!?；;])\s*")


def _unique(*values: list[str]) -> list[str]:
    return list(
        dict.fromkeys(
            value
            for values_ in values
            for value in values_
            if value
        )
    )


def _keywords(*text: str) -> list[str]:
    return _unique(
        *[LATIN_TOKEN_RE.findall(value) for value in text]
    )


def _merged_bbox(blocks: list[DocumentBlock]) -> BoundingBox | None:
    boxes = [block.bbox for block in blocks if block.bbox]
    if not boxes:
        return None

    return BoundingBox(
        x0=min(box.x0 for box in boxes),
        y0=min(box.y0 for box in boxes),
        x1=max(box.x1 for box in boxes),
        y1=max(box.y1 for box in boxes),
    )


def _chunk_id(
    document_id: str,
    version: int,
    level: int,
    index: int,
) -> str:
    return str(
        uuid5(
            NAMESPACE_URL,
            f"{document_id}:{version}:chunk:{level}:{index}",
        )
    )


@dataclass(frozen=True)
class _SentencePiece:
    text: str
    block: DocumentBlock


class StructureAwareChunker:
    """
    Hierarchical chunker.

    L1:
        One parent chunk per document section.

    L2:
        Smaller child chunks generated from the section content.

    Retrieval should normally search L2 chunks and later expand
    to the corresponding L1 parent chunk.
    """

    def __init__(
        self,
        max_chars: int = 500,
        overlap: int = 80,
    ) -> None:
        if max_chars <= 0:
            raise ValueError("max_chars must be positive")

        if not 0 <= overlap < max_chars:
            raise ValueError(
                "overlap must be >= 0 and smaller than max_chars"
            )

        self.max_chars = max_chars
        self.overlap = overlap

    def chunk(
        self,
        document: StructuredDocument,
    ) -> list[ChunkInput]:
        chunks: list[ChunkInput] = []

        sections = self._group_sections(document.blocks)

        parent_index = 0

        for section_blocks in sections:
            if not section_blocks:
                continue

            parent = self._create_parent_chunk(
                document,
                section_blocks,
                parent_index,
            )

            chunks.append(parent)

            children = self._create_child_chunks(
                document,
                section_blocks,
                parent,
                len(chunks),
            )

            chunks.extend(children)
            parent_index += 1

        return chunks

    def _group_sections(
        self,
        blocks: list[DocumentBlock],
    ) -> list[list[DocumentBlock]]:
        """
        Group blocks by their section path.

        A section is identified by its section_path, preserving the
        semantic boundaries created by MarkdownStructureParser.
        """

        sections: list[list[DocumentBlock]] = []
        current_key: tuple[str, ...] | None = None
        current: list[DocumentBlock] = []

        for block in blocks:
            key = tuple(block.section_path)

            if current and key != current_key:
                sections.append(current)
                current = []

            current.append(block)
            current_key = key

        if current:
            sections.append(current)

        return sections

    def _split_by_length(self, text: str) -> list[str]:
        """Split an oversized sentence into bounded character chunks."""
        text = text.strip()

        if not text:
            return []

        if len(text) <= self.max_chars:
            return [text]

        parts: list[str] = []

        start = 0
        while start < len(text):
            end = min(start + self.max_chars, len(text))
            parts.append(text[start:end])

            if end >= len(text):
                break

            start = end

        return parts

    def _create_parent_chunk(
        self,
        document: StructuredDocument,
        blocks: list[DocumentBlock],
        index: int,
    ) -> ChunkInput:
        text = "\n".join(block.text for block in blocks).strip()

        first = blocks[0]
        last = blocks[-1]

        section = section_label(first.section_path)

        context = section or ""

        embedding_text = self._build_embedding_text(
            context=context,
            text=text,
        )

        return ChunkInput(
            chunk_id=_chunk_id(
                document.document_id,
                document.version,
                1,
                index,
            ),
            parent_chunk_id=None,
            level=1,
            text=text,
            embedding_text=embedding_text,
            chunk_type="section",
            section=section,
            section_path=list(first.section_path),
            parent_context=section,
            keywords=_keywords(text, context),
            entities=ChunkEntities(),
            page=first.page,
            bbox=_merged_bbox(blocks),
            char_start=self._min_char_start(blocks),
            char_end=self._max_char_end(blocks),
            confidence=min(
                block.parser_confidence for block in blocks
            ),
            parser_confidence=min(
                block.parser_confidence for block in blocks
            ),
        )

    def _create_child_chunks(
        self,
        document: StructuredDocument,
        blocks: list[DocumentBlock],
        parent: ChunkInput,
        start_index: int,
    ) -> list[ChunkInput]:
        """Create retrieval chunks from the whole section, not per block.

        Blocks define the semantic section boundary. Within one section, their
        sentences form a single stream that is packed by ``max_chars`` and
        ``overlap``. This prevents short adjacent blocks from becoming
        unnecessarily small retrieval chunks.
        """
        pieces: list[_SentencePiece] = []

        for block in blocks:
            text = block.text.strip()
            if not text:
                continue

            sentences = [
                sentence.strip()
                for sentence in SENTENCE_RE.split(text)
                if sentence.strip()
            ]

            if not sentences:
                sentences = [text]

            for sentence in sentences:
                if len(sentence) <= self.max_chars:
                    pieces.append(_SentencePiece(sentence, block))
                else:
                    pieces.extend(
                        _SentencePiece(part, block)
                        for part in self._split_by_length(sentence)
                        if part
                    )

        child_groups = self._pack_sentence_stream(pieces)
        children: list[ChunkInput] = []
        section = parent.section
        section_path = parent.section_path

        for group in child_groups:
            if not group:
                continue

            text = "\n".join(piece.text for piece in group).strip()
            source_blocks = self._unique_blocks(group)
            first_block = source_blocks[0]
            index = start_index + len(children)

            children.append(
                ChunkInput(
                    chunk_id=_chunk_id(
                        document.document_id,
                        document.version,
                        2,
                        index,
                    ),
                    parent_chunk_id=parent.chunk_id,
                    level=2,
                    text=text,
                    embedding_text=self._build_embedding_text(
                        context=section,
                        text=text,
                    ),
                    chunk_type=self._chunk_type(source_blocks),
                    section=section,
                    section_path=list(section_path),
                    parent_context=section,
                    keywords=_keywords(text, section or ""),
                    entities=ChunkEntities(),
                    page=self._common_page(source_blocks),
                    bbox=self._merged_bbox_same_page(source_blocks),
                    char_start=self._min_char_start(source_blocks),
                    char_end=self._max_char_end(source_blocks),
                    confidence=min(
                        block.parser_confidence for block in source_blocks
                    ),
                    parser_confidence=min(
                        block.parser_confidence for block in source_blocks
                    ),
                )
            )

        return children

    def _pack_sentence_stream(
        self,
        pieces: list[_SentencePiece],
    ) -> list[list[_SentencePiece]]:
        """Pack one section's sentence stream into size-bounded chunks."""
        chunks: list[list[_SentencePiece]] = []
        current: list[_SentencePiece] = []
        current_length = 0

        for piece in pieces:
            piece_length = len(piece.text)
            separator_length = 1 if current else 0

            if (
                current
                and current_length + separator_length + piece_length
                > self.max_chars
            ):
                chunks.append(current)

                overlap = self._overlap_pieces(current)
                current = overlap
                current_length = sum(len(item.text) for item in current)
                if current:
                    current_length += len(current) - 1

                separator_length = 1 if current else 0

            current.append(piece)
            current_length += separator_length + piece_length

        if current:
            chunks.append(current)

        return chunks

    def _overlap_pieces(
        self,
        pieces: list[_SentencePiece],
    ) -> list[_SentencePiece]:
        if self.overlap <= 0:
            return []

        result: list[_SentencePiece] = []
        length = 0

        for piece in reversed(pieces):
            extra = len(piece.text) + (1 if result else 0)
            if length + extra > self.overlap:
                break
            result.insert(0, piece)
            length += extra

        return result

    @staticmethod
    def _unique_blocks(
        pieces: list[_SentencePiece],
    ) -> list[DocumentBlock]:
        result: list[DocumentBlock] = []
        seen: set[int] = set()

        for piece in pieces:
            marker = id(piece.block)
            if marker not in seen:
                seen.add(marker)
                result.append(piece.block)

        return result

    @staticmethod
    def _chunk_type(blocks: list[DocumentBlock]) -> str:
        block_types = {block.block_type for block in blocks}
        return next(iter(block_types)) if len(block_types) == 1 else "mixed"

    @staticmethod
    def _common_page(blocks: list[DocumentBlock]) -> int | None:
        pages = {block.page for block in blocks}
        return next(iter(pages)) if len(pages) == 1 else None

    @staticmethod
    def _merged_bbox_same_page(
        blocks: list[DocumentBlock],
    ) -> BoundingBox | None:
        pages = {block.page for block in blocks}
        if len(pages) != 1:
            return None
        return _merged_bbox(blocks)

    @staticmethod
    def _build_embedding_text(
        context: str | None,
        text: str,
    ) -> str:
        if not context:
            return text
        # 拼接embeddingtext
        return f"章节：{context}\n\n{text}"

    @staticmethod
    def _min_char_start(
        blocks: list[DocumentBlock],
    ) -> int | None:
        values = [
            block.char_start
            for block in blocks
            if block.char_start is not None
        ]

        return min(values) if values else None

    @staticmethod
    def _max_char_end(
        blocks: list[DocumentBlock],
    ) -> int | None:
        values = [
            block.char_end
            for block in blocks
            if block.char_end is not None
        ]

        return max(values) if values else None