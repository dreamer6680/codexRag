from fastapi.testclient import TestClient

from app.main import app
from app.auth import AuthenticatedUser, require_user
from app.vector_store import VectorStore
from uuid import UUID


USER = AuthenticatedUser(id=UUID("11111111-1111-1111-1111-111111111111"), email="reader@example.com")


class FakeStorage:
    def __init__(self):
        self.keys = []

    def put_bytes(self, key, data, content_type):
        self.keys.append(key)


class FakeCatalog:
    def upsert_user(self, user):
        assert user == USER

    def upsert(self, record, owner_id):
        assert owner_id == USER.id


def isolate_persistence(monkeypatch):
    storage = FakeStorage()
    monkeypatch.setattr("app.main.object_storage", storage)
    monkeypatch.setattr("app.main.document_catalog", FakeCatalog())
    app.dependency_overrides[require_user] = lambda: USER
    return storage


def test_upload_text_chunks_and_indexes(monkeypatch):
    storage = isolate_persistence(monkeypatch)

    async def fake_index(self, request):
        assert request.document_name == "notes.md"
        assert request.chunks[0].text == "# Hello\nRAG content"
        assert request.owner_id == USER.id
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
    assert all(key.startswith(f"users/{USER.id}/documents/") for key in storage.keys)


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
    app.dependency_overrides[require_user] = lambda: USER
    response = TestClient(app).post(
        "/rag/upload",
        files={"file": ("slides.pptx", b"demo", "application/octet-stream")},
    )

    assert response.status_code == 415
