from fastapi.testclient import TestClient

from app.main import app
from app.vector_store import VectorStore


class FakeStorage:
    def __init__(self):
        self.objects = {}

    def put_bytes(self, key, data, content_type):
        self.objects[key] = (data, content_type)


class FakeCatalog:
    def __init__(self):
        self.records = {}

    def upsert(self, record):
        self.records[record.document_id] = record


def test_index_registers_a_queryable_document_and_replayable_text(monkeypatch):
    storage = FakeStorage()
    catalog = FakeCatalog()

    async def fake_index(self, request):
        return len(request.chunks)

    monkeypatch.setattr("app.main.object_storage", storage)
    monkeypatch.setattr("app.main.document_catalog", catalog)
    monkeypatch.setattr(VectorStore, "index", fake_index)

    response = TestClient(app).post(
        "/rag/index",
        json={
            "document_id": "doc-indexed",
            "document_name": "indexed.md",
            "version": 2,
            "chunks": [{"text": "first chunk"}, {"text": "second chunk"}],
        },
    )

    assert response.status_code == 200
    record = catalog.records["doc-indexed"]
    assert record.status == "ready"
    assert record.version == 2
    assert record.parser == "api-index"
    assert storage.objects[record.markdown_object_key][0] == b"first chunk\n\nsecond chunk"
