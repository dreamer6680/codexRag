from fastapi.testclient import TestClient

from app.main import app
from app.vector_store import VectorStore


class FakeStorage:
    def __init__(self):
        self.objects = {}

    def put_bytes(self, key, data, content_type):
        self.objects[key] = (data, content_type)

    def get_bytes(self, key):
        return self.objects[key][0]

    def stream(self, key):
        return self.objects[key]


class FakeCatalog:
    def __init__(self):
        self.records = {}

    def upsert(self, record):
        self.records[record.document_id] = record

    def list_documents(self):
        return list(self.records.values())

    def get(self, document_id):
        return self.records.get(document_id)


def test_upload_persists_artifacts_and_detail(monkeypatch):
    storage = FakeStorage()
    catalog = FakeCatalog()

    async def fake_index(self, request):
        self.last_request = request
        return len(request.chunks)

    def fake_chunks_for_document(self, document_id, version=None):
        return [
            {
                "index": 0,
                "page": None,
                "section": "chars:0-11",
                "text": "# Hello RAG",
                "char_start": 0,
                "char_end": 11,
                "confidence": 1,
            }
        ]

    monkeypatch.setattr("app.main.object_storage", storage)
    monkeypatch.setattr("app.main.document_catalog", catalog)
    monkeypatch.setattr(VectorStore, "index", fake_index)
    monkeypatch.setattr(VectorStore, "chunks_for_document", fake_chunks_for_document)

    client = TestClient(app)
    upload = client.post(
        "/rag/upload",
        files={"file": ("notes.md", b"# Hello RAG", "text/markdown")},
    )

    assert upload.status_code == 200
    document_id = upload.json()["document_id"]
    detail = client.get(f"/rag/documents/{document_id}")

    assert detail.status_code == 200
    payload = detail.json()
    assert payload["document_name"] == "notes.md"
    assert payload["markdown"] == "# Hello RAG"
    assert payload["chunks"][0]["text"] == "# Hello RAG"
    assert storage.objects[f"documents/{document_id}/v1/parsed.md"][0] == b"# Hello RAG"
