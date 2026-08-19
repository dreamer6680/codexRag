"""Structure-aware chunk creation with resume relationship preservation."""
from __future__ import annotations

import re

from .document_structure import BoundingBox, ChunkEntities, DocumentBlock, StructuredDocument, section_label
from .models import ChunkInput
from .resume_enricher import EnrichedExperience, RESUME_SECTIONS, ResumeEnricher


LATIN_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_.+-]{1,}")


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _keywords(text: str, entities: ChunkEntities) -> list[str]:
    values = (
        entities.companies
        + entities.roles
        + entities.projects
        + entities.dates
        + LATIN_TOKEN_RE.findall(text)
    )
    return _unique(values)


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


class StructureAwareChunker:
    def __init__(self, max_chars: int = 900) -> None:
        if max_chars <= 0:
            raise ValueError("max_chars must be positive")
        self.max_chars = max_chars
        self.enricher = ResumeEnricher()

    def chunk(self, document: StructuredDocument) -> list[ChunkInput]:
        experiences = self.enricher.extract(document)
        by_start = {experience.start_index: experience for experience in experiences}
        covered = {
            index
            for experience in experiences
            for index in range(experience.start_index, experience.end_index)
        }
        chunks: list[ChunkInput] = []

        for index, block in enumerate(document.blocks):
            if index in by_start:
                chunks.extend(self._experience_chunks(by_start[index]))
                continue
            if index in covered:
                continue
            if block.block_type == "heading":
                if experiences and any(section in block.text for section in RESUME_SECTIONS):
                    continue
                continue
            entities = ChunkEntities()
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
                    keywords=_keywords(block.text, entities),
                    entities=entities,
                    bbox=block.bbox,
                    parser_confidence=block.parser_confidence,
                )
            )
        if not chunks:
            headings = [block for block in document.blocks if block.block_type == "heading"]
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

    def _experience_chunks(self, experience: EnrichedExperience) -> list[ChunkInput]:
        section = section_label(experience.section_path) or "工作经历"
        header_lines = [section, f"公司：{experience.company}"]
        if experience.role:
            header_lines.append(f"岗位：{experience.role}")
        if experience.project:
            header_lines.append(f"项目：{experience.project}")
        if experience.dates:
            header_lines.append(f"时间：{'、'.join(experience.dates)}")
        header_lines.append("职责：")
        header = "\n".join(header_lines)
        responsibilities = experience.responsibilities or ["未在原文中识别到明确职责"]
        batches: list[list[str]] = []
        current: list[str] = []
        for responsibility in responsibilities:
            rendered = f"- {responsibility}"
            candidate = "\n".join([header] + current + [rendered])
            if current and len(candidate) > self.max_chars:
                batches.append(current)
                current = [rendered]
            else:
                current.append(rendered)
        if current:
            batches.append(current)

        pages = [block.page for block in experience.source_blocks if block.page is not None]
        starts = [block.char_start for block in experience.source_blocks if block.char_start is not None]
        ends = [block.char_end for block in experience.source_blocks if block.char_end is not None]
        parser_confidence = min(block.parser_confidence for block in experience.source_blocks)
        entities = experience.entities
        return [
            ChunkInput(
                text="\n".join([header] + batch),
                page=min(pages) if pages else None,
                section=experience.parent_context,
                confidence=parser_confidence,
                char_start=min(starts) if starts else None,
                char_end=max(ends) if ends else None,
                chunk_type="resume_experience",
                section_path=experience.section_path + [experience.company],
                parent_context=experience.parent_context,
                keywords=_keywords("\n".join([header] + batch), entities),
                entities=entities,
                bbox=_merged_bbox(experience.source_blocks),
                parser_confidence=parser_confidence,
            )
            for batch in batches
        ]

