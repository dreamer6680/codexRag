import asyncio

from app.document_structure import DocumentBlock, StructuredDocument
from app.ingestion import IngestionService


class RecordingLayoutParser:
    def __init__(self):
        self.raw = None

    def parse(self, document_id, name, raw, version=1):
        self.raw = raw
        return StructuredDocument(
            document_id=document_id,
            name=name,
            version=version,
            parser="pymupdf-layout",
            markdown="# Resume\n\nFastGPT",
            blocks=[
                DocumentBlock(block_type="heading", text="Resume", section_path=["Resume"], heading_level=1),
                DocumentBlock(block_type="paragraph", text="FastGPT", section_path=["Resume"], page=1),
            ],
        )


def test_text_pdf_uses_raw_layout_parser():
    layout = RecordingLayoutParser()

    async def mineru_must_not_run(*args):
        raise AssertionError("text PDFs must not use MinerU")

    result = asyncio.run(
        IngestionService(layout_parser=layout, mineru_parser=mineru_must_not_run).parse(
            "doc-1", "resume.pdf", b"raw-pdf", "application/pdf", pdf_type="TextBased"
        )
    )

    assert layout.raw == b"raw-pdf"
    assert result.parser == "pymupdf-layout"
    assert result.request.chunks[0].text == "FastGPT"
    assert result.request.chunks[0].page == 1


def test_scanned_pdf_uses_mineru_then_structural_markdown_parser():
    async def mineru_parser(filename, raw, content_type):
        assert filename == "scan.pdf"
        assert raw == b"scan"
        return "## 工作经历\n\n某某科技有限公司\n\n- 维护知识库"

    result = asyncio.run(
        IngestionService(mineru_parser=mineru_parser).parse(
            "doc-2", "scan.pdf", b"scan", "application/pdf", pdf_type="Scanned"
        )
    )

    assert result.parser == "mineru-structure"
    assert "某某科技有限公司" in result.markdown
    assert result.request.chunks[0].chunk_type == "resume_experience"


def test_markdown_uses_common_structure_pipeline():
    result = asyncio.run(
        IngestionService().parse(
            "doc-3", "notes.md", b"# Title\n\nBody", "text/markdown"
        )
    )

    assert result.parser == "markdown-structure"
    assert result.request.chunks[0].section_path == ["Title"]

