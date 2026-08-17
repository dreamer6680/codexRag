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
        self.reserved = set()

    def upsert(self, record):
        self.records[record.document_id] = record

    def get(self, document_id):
        return self.records.get(document_id)

    def reserve_index_version(self, document_id, document_name, version):
        existing = self.records.get(document_id)
        if existing and existing.version >= version:
            return False
        self.reserved.add((document_id, version))
        return True

    def finalize_index(self, record):
        if (record.document_id, record.version) not in self.reserved:
            return False
        self.records[record.document_id] = record
        return True

    def mark_index_failed(self, document_id, version):
        pass


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


def test_index_rejects_blank_chunks(monkeypatch):
    storage = FakeStorage()
    catalog = FakeCatalog()

    async def must_not_index(self, request):
        raise AssertionError("blank chunks must fail validation before indexing")

    monkeypatch.setattr("app.main.object_storage", storage)
    monkeypatch.setattr("app.main.document_catalog", catalog)
    monkeypatch.setattr(VectorStore, "index", must_not_index)

    response = TestClient(app).post(
        "/rag/index",
        json={
            "document_id": "blank-doc",
            "document_name": "blank.md",
            "version": 1,
            "chunks": [{"text": "   "}],
        },
    )

    assert response.status_code == 422
    assert storage.objects == {}
    assert catalog.records == {}


def test_index_requires_a_strictly_newer_document_version(monkeypatch):
    storage = FakeStorage()
    catalog = FakeCatalog()

    class ExistingRecord:
        version = 2

    catalog.records["doc-indexed"] = ExistingRecord()

    async def must_not_index(self, request):
        raise AssertionError("same version must be rejected before Qdrant upsert")

    monkeypatch.setattr("app.main.object_storage", storage)
    monkeypatch.setattr("app.main.document_catalog", catalog)
    monkeypatch.setattr(VectorStore, "index", must_not_index)

    response = TestClient(app).post(
        "/rag/index",
        json={
            "document_id": "doc-indexed",
            "document_name": "indexed.md",
            "version": 2,
            "chunks": [{"text": "replacement"}],
        },
    )

    assert response.status_code == 409
    assert storage.objects == {}


def test_index_uses_atomic_reservation_before_qdrant(monkeypatch):
    storage = FakeStorage()

    class RejectedReservationCatalog(FakeCatalog):
        def reserve_index_version(self, document_id, document_name, version):
            return False

    catalog = RejectedReservationCatalog()

    async def must_not_index(self, request):
        raise AssertionError("rejected reservation must not reach Qdrant")

    monkeypatch.setattr("app.main.object_storage", storage)
    monkeypatch.setattr("app.main.document_catalog", catalog)
    monkeypatch.setattr(VectorStore, "index", must_not_index)

    response = TestClient(app).post(
        "/rag/index",
        json={
            "document_id": "doc-indexed",
            "document_name": "indexed.md",
            "version": 2,
            "chunks": [{"text": "replacement"}],
        },
    )

    assert response.status_code == 409
    assert storage.objects == {}
