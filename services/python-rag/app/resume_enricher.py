"""Deterministic resume relationship extraction over normalized blocks."""
from __future__ import annotations

import re

from pydantic import BaseModel, Field

from .document_structure import ChunkEntities, DocumentBlock, StructuredDocument, section_label


COMPANY_RE = re.compile(
    r"([\u4e00-\u9fffA-Za-z0-9·]{2,}?(?:股份有限公司|有限责任公司|有限公司|集团|研究院|工作室|事务所|学校|大学))"
)
ROLE_RE = re.compile(r"(?:全栈|前端|后端|研发|开发|工程师|架构师|产品|测试|算法|实习|经理|负责人|顾问|设计师)")
DATE_RE = re.compile(
    r"(?:19|20)\d{2}\s*[./年-]\s*\d{1,2}\s*(?:月)?\s*(?:[-—~至]|到)\s*"
    r"(?:(?:19|20)\d{2}\s*[./年-]\s*\d{1,2}\s*(?:月)?|至今)"
)
LATIN_IDENTIFIER_RE = re.compile(r"[A-Za-z][A-Za-z0-9_.+-]{2,}")
RESUME_SECTIONS = ("工作经历", "项目经历", "实习经历")


class EnrichedExperience(BaseModel):
    start_index: int
    end_index: int
    section_path: list[str] = Field(default_factory=list)
    company: str
    role: str | None = None
    project: str | None = None
    dates: list[str] = Field(default_factory=list)
    responsibilities: list[str] = Field(default_factory=list)
    source_blocks: list[DocumentBlock] = Field(default_factory=list)

    @property
    def entities(self) -> ChunkEntities:
        return ChunkEntities(
            companies=[self.company],
            roles=[self.role] if self.role else [],
            projects=[self.project] if self.project else [],
            dates=self.dates,
        )

    @property
    def parent_context(self) -> str:
        root = section_label(self.section_path) or "工作经历"
        return f"{root} / {self.company}"


def _in_resume_experience(block: DocumentBlock) -> bool:
    context = " / ".join(block.section_path)
    return any(section in context for section in RESUME_SECTIONS)


def _resume_section_path(block: DocumentBlock) -> list[str]:
    for index, part in enumerate(block.section_path):
        if any(section in part for section in RESUME_SECTIONS):
            return block.section_path[index:]
    return ["工作经历"]


class ResumeEnricher:
    def extract(self, document: StructuredDocument) -> list[EnrichedExperience]:
        results: list[EnrichedExperience] = []
        current: dict[str, object] | None = None

        def flush(end_index: int) -> None:
            nonlocal current
            if current is None:
                return
            current["end_index"] = end_index
            results.append(EnrichedExperience(**current))
            current = None

        for index, block in enumerate(document.blocks):
            if block.block_type == "heading":
                flush(index)
                continue
            if not _in_resume_experience(block):
                flush(index)
                continue
            text = block.text.strip()
            company_match = COMPANY_RE.search(text)
            if company_match:
                flush(index)
                current = {
                    "start_index": index,
                    "end_index": index + 1,
                    "section_path": _resume_section_path(block),
                    "company": company_match.group(1),
                    "dates": [match.group(0) for match in DATE_RE.finditer(text)],
                    "responsibilities": [],
                    "source_blocks": [block],
                }
                continue
            if current is None:
                continue
            source_blocks = current["source_blocks"]
            assert isinstance(source_blocks, list)
            previous_block = source_blocks[-1]
            source_blocks.append(block)
            dates = current["dates"]
            assert isinstance(dates, list)
            dates.extend(match.group(0) for match in DATE_RE.finditer(text) if match.group(0) not in dates)

            if block.block_type == "list_item":
                responsibilities = current["responsibilities"]
                assert isinstance(responsibilities, list)
                responsibilities.append(text)
            elif current.get("role") is None and ROLE_RE.search(text) and len(text) <= 40:
                role = re.sub(r"^(?:岗位|职位)\s*[:：]\s*", "", text)
                current["role"] = re.split(r"\s+|[|，,]", role, maxsplit=1)[0]
            elif current.get("project") is None and len(text) <= 60 and (
                text.startswith(("项目：", "项目:")) or LATIN_IDENTIFIER_RE.search(text)
            ):
                project = re.sub(r"^项目\s*[:：]\s*", "", text)
                current["project"] = re.split(r"[，,|]", project, maxsplit=1)[0].strip()
            else:
                responsibilities = current["responsibilities"]
                assert isinstance(responsibilities, list)
                responsibility = re.sub(r"^(?:职责|工作内容)\s*[:：]\s*", "", text)
                if responsibilities and previous_block.block_type in {"list_item", "paragraph"}:
                    responsibilities[-1] = f"{responsibilities[-1]} {responsibility}"
                else:
                    responsibilities.append(responsibility)

        flush(len(document.blocks))
        return results
