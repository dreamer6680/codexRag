from app.document_structure import (
    BoundingBox,
    ChunkEntities,
    DocumentBlock,
    StructuredDocument,
    normalize_text,
    section_label,
)
from app.models import ChunkInput, DocumentChunkDetail


def test_normalized_block_preserves_layout_and_section_ancestry():
    block = DocumentBlock(
        block_type="paragraph",
        text="  珠海环届云有限公司\n 全栈研发  ",
        page=1,
        bbox=BoundingBox(x0=320, y0=120, x1=560, y1=180),
        section_path=["工作经历", "珠海环届云有限公司"],
        char_start=12,
        char_end=34,
        parser_confidence=0.92,
    )

    assert block.text == "珠海环届云有限公司 全栈研发"
    assert block.section == "工作经历 / 珠海环届云有限公司"
    assert block.bbox.model_dump() == {"x0": 320.0, "y0": 120.0, "x1": 560.0, "y1": 180.0}


def test_structured_document_rejects_empty_blocks():
    try:
        StructuredDocument(document_id="doc-1", name="empty.pdf", blocks=[])
    except ValueError as exc:
        assert "block" in str(exc).lower()
    else:
        raise AssertionError("empty structured documents must be rejected")


def test_chunk_models_round_trip_structural_metadata():
    entities = ChunkEntities(
        companies=["珠海环届云有限公司"],
        roles=["全栈研发"],
        projects=["FastGPT"],
    )
    chunk = ChunkInput(
        text="公司：珠海环届云有限公司\n岗位：全栈研发\n项目：FastGPT",
        page=1,
        section_path=["工作经历", "珠海环届云有限公司"],
        chunk_type="resume_experience",
        parent_context="工作经历",
        keywords=["珠海环届云有限公司", "全栈研发", "FastGPT"],
        entities=entities,
        bbox=BoundingBox(x0=300, y0=100, x1=560, y1=500),
        parser_confidence=0.88,
    )

    detail = DocumentChunkDetail(index=0, **chunk.model_dump())

    assert detail.chunk_type == "resume_experience"
    assert detail.section_path == ["工作经历", "珠海环届云有限公司"]
    assert detail.entities.projects == ["FastGPT"]
    assert detail.parser_confidence == 0.88


def test_normalization_helpers_are_deterministic():
    assert normalize_text("  A\r\n\tB  ") == "A B"
    assert section_label([" 工作经历 ", "", "FastGPT"]) == "工作经历 / FastGPT"
