import pytest

from app.document_processor import DocumentProcessor


def test_processor_chunks_with_overlap():
    processor = DocumentProcessor(chunk_size=10, chunk_overlap=2)
    document = processor.from_text("doc-1", "demo", "1234567890abcdefghij")

    request = processor.to_index_request(document)

    assert [chunk.text for chunk in request.chunks] == ["1234567890", "90abcdefgh", "ghij"]


def test_processor_records_chunk_offsets():
    processor = DocumentProcessor(chunk_size=10, chunk_overlap=2)
    document = processor.from_text("doc-1", "demo.md", "1234567890abcdefghij")

    request = processor.to_index_request(document)

    assert [(chunk.char_start, chunk.char_end, chunk.text) for chunk in request.chunks] == [
        (0, 10, "1234567890"),
        (8, 18, "90abcdefgh"),
        (16, 20, "ghij"),
    ]


def test_processor_rejects_empty_document():
    processor = DocumentProcessor()
    document = processor.from_text("doc-1", "empty", "   ")

    with pytest.raises(ValueError, match="empty"):
        processor.to_index_request(document)
