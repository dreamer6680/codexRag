"""Deterministic Markdown/plain-text parser that preserves semantic boundaries."""
import re

from .document_structure import DocumentBlock, StructuredDocument, normalize_text


HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
LIST_RE = re.compile(r"^(\s*)(?:[-*+]\s+|\d+[.)]\s+)(.+)$")
TABLE_SEPARATOR_RE = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$")


class MarkdownStructureParser:
    def parse(
        self,
        document_id: str,
        name: str,
        content: str,
        version: int = 1,
    ) -> StructuredDocument:
        if not content.strip():
            raise ValueError("document content is empty")

        blocks: list[DocumentBlock] = []
        headings: list[str] = []
        paragraph_lines: list[str] = []
        paragraph_start: int | None = None
        offset = 0
        in_code = False
        code_lines: list[str] = []
        code_start: int | None = None

        def flush_paragraph(end: int) -> None:
            nonlocal paragraph_lines, paragraph_start
            text = normalize_text("\n".join(paragraph_lines))
            if text:
                blocks.append(
                    DocumentBlock(
                        block_type="paragraph",
                        text=text,
                        section_path=list(headings),
                        char_start=paragraph_start,
                        char_end=end,
                    )
                )
            paragraph_lines = []
            paragraph_start = None

        for raw_line in content.splitlines(keepends=True):
            line = raw_line.rstrip("\r\n")
            line_end = offset + len(raw_line)

            if line.strip().startswith("```"):
                flush_paragraph(offset)
                if in_code:
                    code_text = "\n".join(code_lines).strip()
                    if code_text:
                        blocks.append(
                            DocumentBlock(
                                block_type="code",
                                text=code_text,
                                section_path=list(headings),
                                char_start=code_start,
                                char_end=line_end,
                            )
                        )
                    code_lines = []
                    code_start = None
                else:
                    code_start = offset
                in_code = not in_code
                offset = line_end
                continue

            if in_code:
                code_lines.append(line)
                offset = line_end
                continue

            heading = HEADING_RE.match(line)
            list_item = LIST_RE.match(line)
            is_table = line.strip().startswith("|") and line.strip().endswith("|")

            if heading:
                flush_paragraph(offset)
                level = len(heading.group(1))
                title = normalize_text(heading.group(2))
                headings = headings[: level - 1]
                headings.append(title)
                blocks.append(
                    DocumentBlock(
                        block_type="heading",
                        text=title,
                        section_path=list(headings),
                        heading_level=level,
                        char_start=offset,
                        char_end=line_end,
                    )
                )
            elif list_item:
                flush_paragraph(offset)
                blocks.append(
                    DocumentBlock(
                        block_type="list_item",
                        text=list_item.group(2),
                        section_path=list(headings),
                        list_level=len(list_item.group(1).replace("\t", "    ")) // 2,
                        char_start=offset,
                        char_end=line_end,
                    )
                )
            elif is_table:
                flush_paragraph(offset)
                if not TABLE_SEPARATOR_RE.match(line):
                    cells = [normalize_text(cell) for cell in line.strip().strip("|").split("|")]
                    blocks.append(
                        DocumentBlock(
                            block_type="table_row",
                            text=" | ".join(cell for cell in cells if cell),
                            section_path=list(headings),
                            char_start=offset,
                            char_end=line_end,
                        )
                    )
            elif not line.strip():
                flush_paragraph(offset)
            else:
                if paragraph_start is None:
                    paragraph_start = offset
                paragraph_lines.append(line)
            offset = line_end

        if in_code and code_lines:
            blocks.append(
                DocumentBlock(
                    block_type="code",
                    text="\n".join(code_lines),
                    section_path=list(headings),
                    char_start=code_start,
                    char_end=len(content),
                    parser_confidence=0.9,
                )
            )
        else:
            flush_paragraph(len(content))

        if not blocks:
            raise ValueError("document content is empty")
        parser = "markdown-structure" if name.lower().endswith(".md") else "text-structure"
        return StructuredDocument(
            document_id=document_id,
            name=name,
            blocks=blocks,
            markdown=content.strip(),
            parser=parser,
            version=version,
        )

