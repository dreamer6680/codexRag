import pytest

from app.document_processor import DocumentProcessor


def test_processor_preserves_heading_ancestry_and_paragraphs():
    processor = DocumentProcessor()
    document = processor.from_text(
        "doc-1",
        "resume.md",
        "# 个人简历\n\n## 工作经历\n\n珠海环届云有限公司\n\n### FastGPT\n\n负责知识库同步。",
    )

    structured = processor.structure(document)

    paragraphs = [block for block in structured.blocks if block.block_type == "paragraph"]
    assert [(block.text, block.section_path) for block in paragraphs] == [
        ("珠海环届云有限公司", ["个人简历", "工作经历"]),
        ("负责知识库同步。", ["个人简历", "工作经历", "FastGPT"]),
    ]


def test_processor_keeps_list_items_atomic():
    processor = DocumentProcessor()
    document = processor.from_text(
        "doc-1",
        "resume.md",
        "## 工作职责\n- 将 Hugo 文档迁移到 Fumadoc\n- 实现 Redis 定时同步知识库",
    )

    request = processor.to_index_request(document)

    assert [chunk.text for chunk in request.chunks] == [
        "将 Hugo 文档迁移到 Fumadoc",
        "实现 Redis 定时同步知识库",
    ]
    assert all(chunk.chunk_type == "list_item" for chunk in request.chunks)
    assert all(chunk.section_path == ["工作职责"] for chunk in request.chunks)


def test_processor_keeps_markdown_table_rows_intact():
    processor = DocumentProcessor()
    document = processor.from_text(
        "doc-1",
        "facts.md",
        "## 基本信息\n| 字段 | 内容 |\n| --- | --- |\n| 论文题目 | 智能旅游规划助手设计与实现 |",
    )

    structured = processor.structure(document)
    rows = [block for block in structured.blocks if block.block_type == "table_row"]

    assert [row.text for row in rows] == [
        "字段 | 内容",
        "论文题目 | 智能旅游规划助手设计与实现",
    ]
    assert all(row.section_path == ["基本信息"] for row in rows)


def test_processor_plain_text_uses_paragraph_boundaries():
    processor = DocumentProcessor()
    document = processor.from_text("doc-1", "notes.txt", "第一段。\n仍是第一段。\n\n第二段。")

    request = processor.to_index_request(document)

    assert [chunk.text for chunk in request.chunks] == ["第一段。 仍是第一段。", "第二段。"]


def test_processor_rejects_empty_document():
    processor = DocumentProcessor()
    document = processor.from_text("doc-1", "empty", "   ")

    with pytest.raises(ValueError, match="empty"):
        processor.to_index_request(document)
