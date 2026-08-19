"""Raw PDF layout extraction and deterministic multi-column reading order."""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from statistics import median
import re
from typing import Iterable, Mapping, Sequence

from .document_structure import BoundingBox, DocumentBlock, StructuredDocument, normalize_text


PAGE_NUMBER_RE = re.compile(r"\d+")
LIST_PREFIX_RE = re.compile(r"^\s*(?:[•●▪◦‣⁃*-]|\d+[.)、])\s*")


@dataclass(frozen=True)
class RawLayoutBlock:
    text: str
    page: int
    page_width: float
    page_height: float
    bbox: tuple[float, float, float, float]
    font_size: float
    bold: bool

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> RawLayoutBlock:
        raw_bbox = value["bbox"]
        if not isinstance(raw_bbox, Sequence) or len(raw_bbox) != 4:
            raise ValueError("layout block bbox must contain four coordinates")
        return cls(
            text=normalize_text(str(value["text"])),
            page=int(value["page"]),
            page_width=float(value["page_width"]),
            page_height=float(value["page_height"]),
            bbox=tuple(float(item) for item in raw_bbox),
            font_size=float(value.get("font_size", 0)),
            bold=bool(value.get("bold", False)),
        )

    @property
    def x0(self) -> float:
        return self.bbox[0]

    @property
    def y0(self) -> float:
        return self.bbox[1]

    @property
    def x1(self) -> float:
        return self.bbox[2]

    @property
    def y1(self) -> float:
        return self.bbox[3]

    @property
    def center_x(self) -> float:
        return (self.x0 + self.x1) / 2


def _marginal_key(block: RawLayoutBlock) -> str | None:
    near_top = block.y0 <= block.page_height * 0.08
    near_bottom = block.y1 >= block.page_height * 0.92
    if not (near_top or near_bottom):
        return None
    return PAGE_NUMBER_RE.sub("#", normalize_text(block.text).lower())


def remove_repeated_marginals(blocks: Iterable[RawLayoutBlock]) -> list[RawLayoutBlock]:
    rows = list(blocks)
    pages_by_key: dict[str, set[int]] = defaultdict(set)
    for block in rows:
        key = _marginal_key(block)
        if key:
            pages_by_key[key].add(block.page)
    repeated = {key for key, pages in pages_by_key.items() if len(pages) >= 2}
    return [block for block in rows if _marginal_key(block) not in repeated]


def _order_region(blocks: list[RawLayoutBlock], page_width: float) -> list[RawLayoutBlock]:
    if len(blocks) < 2:
        return blocks
    centers = sorted(block.center_x for block in blocks)
    gaps = [(centers[index + 1] - centers[index], index) for index in range(len(centers) - 1)]
    largest_gap, gap_index = max(gaps, default=(0, 0))
    if largest_gap < page_width * 0.18:
        return sorted(blocks, key=lambda block: (block.y0, block.x0))
    split_x = (centers[gap_index] + centers[gap_index + 1]) / 2
    left = [block for block in blocks if block.center_x <= split_x]
    right = [block for block in blocks if block.center_x > split_x]
    if not left or not right:
        return sorted(blocks, key=lambda block: (block.y0, block.x0))
    return sorted(left, key=lambda block: (block.y0, block.x0)) + sorted(
        right, key=lambda block: (block.y0, block.x0)
    )


def order_layout_blocks(blocks: Iterable[RawLayoutBlock]) -> list[RawLayoutBlock]:
    by_page: dict[int, list[RawLayoutBlock]] = defaultdict(list)
    for block in blocks:
        if normalize_text(block.text):
            by_page[block.page].append(block)

    ordered: list[RawLayoutBlock] = []
    for page in sorted(by_page):
        page_blocks = by_page[page]
        page_width = page_blocks[0].page_width
        full_width = sorted(
            [block for block in page_blocks if (block.x1 - block.x0) >= page_width * 0.7],
            key=lambda block: (block.y0, block.x0),
        )
        remaining = [block for block in page_blocks if block not in full_width]
        lower_bound = float("-inf")
        for anchor in full_width:
            region = [block for block in remaining if lower_bound <= block.y0 < anchor.y0]
            ordered.extend(_order_region(region, page_width))
            remaining = [block for block in remaining if block not in region]
            ordered.append(anchor)
            lower_bound = anchor.y1
        ordered.extend(_order_region(remaining, page_width))
    return ordered


class PdfLayoutParser:
    def parse(
        self,
        document_id: str,
        name: str,
        raw: bytes,
        version: int = 1,
    ) -> StructuredDocument:
        import pymupdf

        try:
            pdf = pymupdf.open(stream=raw, filetype="pdf")
        except Exception as exc:
            raise ValueError(f"invalid PDF: {exc}") from exc
        try:
            blocks: list[RawLayoutBlock] = []
            for page_index, page in enumerate(pdf):
                page_dict = page.get_text("dict")
                for raw_block in page_dict.get("blocks", []):
                    for line in raw_block.get("lines", []):
                        spans = [span for span in line.get("spans", []) if normalize_text(span.get("text", ""))]
                        if not spans:
                            continue
                        text = normalize_text("".join(str(span.get("text", "")) for span in spans))
                        bbox = line.get("bbox") or raw_block.get("bbox")
                        if not text or not bbox:
                            continue
                        blocks.append(
                            RawLayoutBlock(
                                text=text,
                                page=page_index + 1,
                                page_width=float(page.rect.width),
                                page_height=float(page.rect.height),
                                bbox=tuple(float(value) for value in bbox),
                                font_size=max(float(span.get("size", 0)) for span in spans),
                                bold=any(
                                    "bold" in str(span.get("font", "")).lower()
                                    or bool(int(span.get("flags", 0)) & 16)
                                    for span in spans
                                ),
                            )
                        )
        finally:
            pdf.close()
        if not blocks:
            raise ValueError("PDF contains no extractable text")
        return self.from_blocks(document_id, name, blocks, version)

    def from_blocks(
        self,
        document_id: str,
        name: str,
        blocks: Iterable[RawLayoutBlock],
        version: int = 1,
    ) -> StructuredDocument:
        rows = remove_repeated_marginals(blocks)
        ordered = order_layout_blocks(rows)
        if not ordered:
            raise ValueError("PDF contains no usable layout blocks")

        common_font = median([block.font_size for block in ordered if block.font_size > 0] or [10])
        headings: list[str] = []
        output: list[DocumentBlock] = []
        for raw_block in ordered:
            is_heading = raw_block.font_size >= common_font * 1.25 or (
                raw_block.bold and raw_block.font_size >= common_font * 1.18
            )
            is_list = bool(LIST_PREFIX_RE.match(raw_block.text))
            text = LIST_PREFIX_RE.sub("", raw_block.text) if is_list else raw_block.text
            if is_heading:
                level = 1 if raw_block.font_size >= common_font * 1.25 else 2
                headings = headings[: level - 1]
                headings.append(text)
                block_type = "heading"
                section_path = list(headings)
            else:
                block_type = "list_item" if is_list else "paragraph"
                section_path = list(headings)
                level = None
            output.append(
                DocumentBlock(
                    block_type=block_type,
                    text=text,
                    page=raw_block.page,
                    bbox=BoundingBox(
                        x0=raw_block.x0,
                        y0=raw_block.y0,
                        x1=raw_block.x1,
                        y1=raw_block.y1,
                    ),
                    section_path=section_path,
                    heading_level=level,
                    parser_confidence=0.95,
                )
            )

        markdown_lines = []
        for block in output:
            if block.block_type == "heading":
                markdown_lines.append(f"{'#' * (block.heading_level or 1)} {block.text}")
            elif block.block_type == "list_item":
                markdown_lines.append(f"- {block.text}")
            else:
                markdown_lines.append(block.text)
        return StructuredDocument(
            document_id=document_id,
            name=name,
            blocks=output,
            markdown="\n\n".join(markdown_lines),
            parser="pymupdf-layout",
            version=version,
        )
