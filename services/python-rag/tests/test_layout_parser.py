import json
from pathlib import Path

import pytest

from app.layout_parser import PdfLayoutParser, RawLayoutBlock, order_layout_blocks, remove_repeated_marginals


FIXTURE = Path(__file__).parent / "fixtures" / "two_column_resume_blocks.json"


def load_blocks():
    return [RawLayoutBlock.from_mapping(item) for item in json.loads(FIXTURE.read_text(encoding="utf-8"))]


def test_two_column_reading_order_does_not_interleave_rows():
    ordered = order_layout_blocks(load_blocks())

    assert [block.text for block in ordered] == [
        "个人简历",
        "技能",
        "Java Python",
        "教育经历",
        "杭州电子科技大学",
        "工作经历",
        "珠海环届云有限公司",
        "全栈研发",
        "FastGPT",
        "• 实现 Redis 定时同步知识库",
    ]


def test_repeated_headers_and_footers_are_removed_but_body_is_kept():
    blocks = [
        RawLayoutBlock("孟哲简历", 1, 600, 800, (20, 10, 580, 30), 8, False),
        RawLayoutBlock("第一页正文", 1, 600, 800, (20, 100, 580, 140), 10, False),
        RawLayoutBlock("第 1 页", 1, 600, 800, (260, 770, 340, 790), 8, False),
        RawLayoutBlock("孟哲简历", 2, 600, 800, (20, 10, 580, 30), 8, False),
        RawLayoutBlock("第二页正文", 2, 600, 800, (20, 100, 580, 140), 10, False),
        RawLayoutBlock("第 2 页", 2, 600, 800, (260, 770, 340, 790), 8, False),
    ]

    kept = remove_repeated_marginals(blocks)

    assert [block.text for block in kept] == ["第一页正文", "第二页正文"]


def test_layout_blocks_become_headings_lists_and_paragraphs():
    structured = PdfLayoutParser().from_blocks("resume", "resume.pdf", load_blocks())
    by_text = {block.text: block for block in structured.blocks}

    assert by_text["工作经历"].block_type == "heading"
    assert by_text["工作经历"].section_path == ["工作经历"]
    assert by_text["珠海环届云有限公司"].section_path == ["工作经历"]
    assert by_text["实现 Redis 定时同步知识库"].block_type == "list_item"
    assert by_text["实现 Redis 定时同步知识库"].page == 1
    assert by_text["实现 Redis 定时同步知识库"].bbox.x0 == 310


def test_pdf_parser_reads_coordinates_from_pdf_bytes():
    pymupdf = pytest.importorskip("pymupdf")
    pdf = pymupdf.open()
    page = pdf.new_page(width=600, height=800)
    page.insert_text((40, 60), "Resume", fontsize=20)
    page.insert_text((320, 140), "FastGPT", fontsize=12)
    raw = pdf.tobytes()
    pdf.close()

    structured = PdfLayoutParser().parse("doc-1", "resume.pdf", raw)

    assert [block.text for block in structured.blocks] == ["Resume", "FastGPT"]
    assert structured.blocks[1].bbox.x0 >= 300
    assert structured.parser == "pymupdf-layout"
