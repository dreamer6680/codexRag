from fastapi.testclient import TestClient

from app.main import app
from app.vector_store import VectorStore


class FakeStorage:
    def put_bytes(self, key, data, content_type):
        pass


class FakeCatalog:
    def upsert(self, record):
        pass


def isolate_persistence(monkeypatch):
    monkeypatch.setattr("app.main.object_storage", FakeStorage())
    monkeypatch.setattr("app.main.document_catalog", FakeCatalog())


def test_upload_text_chunks_and_indexes(monkeypatch):
    isolate_persistence(monkeypatch)

    async def fake_index(self, request):
        assert request.document_name == "notes.md"
        assert request.chunks[0].text == "# Hello\nRAG content"
        return len(request.chunks)

    monkeypatch.setattr(VectorStore, "index", fake_index)
    response = TestClient(app).post(
        "/rag/upload",
        files={"file": ("notes.md", b"# Hello\nRAG content", "text/markdown")},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert response.json()["indexed_chunks"] == 1
    assert response.json()["parser"] == "plain-text"


def test_upload_preparsed_pdf_does_not_require_mineru(monkeypatch):
    isolate_persistence(monkeypatch)

    async def fake_index(self, request):
        assert request.chunks[0].text == "# Extracted PDF"
        return 1

    monkeypatch.setattr(VectorStore, "index", fake_index)
    response = TestClient(app).post(
        "/rag/upload",
        files={"file": ("report.pdf", b"%PDF-placeholder", "application/pdf")},
        data={"extracted_markdown": "# Extracted PDF", "parser": "pdf-inspector"},
    )

    assert response.status_code == 200
    assert response.json()["parser"] == "pdf-inspector"


def test_upload_rejects_unsupported_format():
    response = TestClient(app).post(
        "/rag/upload",
        files={"file": ("slides.pptx", b"demo", "application/octet-stream")},
    )

    assert response.status_code == 415
