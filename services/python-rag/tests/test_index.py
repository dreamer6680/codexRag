import pytest
from fastapi.testclient import TestClient
from uuid import UUID

from app.auth import AuthenticatedUser, require_user
from app.main import app
from app.vector_store import VectorStore

USER = AuthenticatedUser(id=UUID("11111111-1111-1111-1111-111111111111"), email="reader@example.com")


@pytest.fixture(autouse=True)
def authenticated_user():
    app.dependency_overrides[require_user] = lambda: USER
    yield
    app.dependency_overrides.pop(require_user, None)


class FakeStorage:
    def __init__(self):
        self.objects = {}

    def put_bytes(self, key, data, content_type):
        self.objects[key] = (data, content_type)


class FakeCatalog:
    def __init__(self):
        self.records = {}
        self.reserved = set()
        self.latest_attempted_versions = {}
        self.failed = set()

    def upsert_user(self, user):
        pass

    def upsert(self, record, owner_id=None):
        self.records[record.document_id] = record

    def get(self, document_id, owner_id=None):
        return self.records.get(document_id)

    def reserve_index_version(self, owner_id, document_id, document_name, version):
        existing = self.records.get(document_id)
        latest = self.latest_attempted_versions.get(
            document_id, existing.version if existing else 0
        )
        if version <= latest:
            return False
        self.latest_attempted_versions[document_id] = version
        self.reserved.add((document_id, version))
        return True

    def finalize_index(self, record, owner_id):
        if (record.document_id, record.version) not in self.reserved:
            return False
        self.records[record.document_id] = record
        return True

    def mark_index_failed(self, owner_id, document_id, version):
        self.failed.add((document_id, version))


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
        def reserve_index_version(self, owner_id, document_id, document_name, version):
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


def test_failed_index_keeps_previous_ready_version_and_cannot_retry_same_version(monkeypatch):
    storage = FakeStorage()
    catalog = FakeCatalog()

    class ExistingRecord:
        document_id = "doc-indexed"
        version = 1
        status = "ready"

    previous = ExistingRecord()
    catalog.records["doc-indexed"] = previous

    async def failed_index(self, request):
        raise RuntimeError("qdrant unavailable")

    monkeypatch.setattr("app.main.object_storage", storage)
    monkeypatch.setattr("app.main.document_catalog", catalog)
    monkeypatch.setattr(VectorStore, "index", failed_index)

    payload = {
        "document_id": "doc-indexed",
        "document_name": "indexed.md",
        "version": 2,
        "chunks": [{"text": "replacement"}],
    }
    client = TestClient(app, raise_server_exceptions=False)
    first = client.post("/rag/index", json=payload)
    retry = client.post("/rag/index", json=payload)

    assert first.status_code == 500
    assert retry.status_code == 409
    assert catalog.records["doc-indexed"] is previous
    assert ("doc-indexed", 2) in catalog.failed
