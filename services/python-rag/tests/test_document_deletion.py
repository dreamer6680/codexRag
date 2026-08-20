from contextlib import nullcontext
from datetime import datetime, timezone
from uuid import UUID, uuid4

from app.document_catalog import DocumentCatalog
from app.models import ChatMessage
from app.object_storage import ObjectStorage
from app.vector_store import VectorStore


OWNER = uuid4()
OTHER_OWNER = uuid4()


class Result:
    def __init__(self, one=None, many=None):
        self.one = one
        self.many = many or []

    def fetchone(self):
        return self.one

    def fetchall(self):
        return self.many


class RecordingConnection:
    def __init__(self, live_owner=None, tombstone_owner=None, live_ids=None):
        self.live_owner = live_owner
        self.tombstone_owner = tombstone_owner
        self.live_ids = live_ids or []
        self.statements = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params=None):
        normalized = " ".join(str(sql).split())
        self.statements.append(normalized)
        if "SELECT owner_id FROM rag_documents" in normalized:
            return Result({"owner_id": self.live_owner} if self.live_owner else None)
        if "SELECT owner_id FROM rag_document_tombstones" in normalized:
            return Result({"owner_id": self.tombstone_owner} if self.tombstone_owner else None)
        if "SELECT d.document_id" in normalized:
            return Result(many=[{"document_id": item} for item in self.live_ids])
        return Result()


def catalog_with(monkeypatch, **connection_kwargs):
    connection = RecordingConnection(**connection_kwargs)
    catalog = DocumentCatalog()
    monkeypatch.setattr(catalog, "ensure_schema", lambda: None)
    monkeypatch.setattr(catalog, "_connect", lambda: nullcontext(connection))
    return catalog, connection


def test_begin_delete_writes_tombstone_before_removing_catalog(monkeypatch):
    catalog, connection = catalog_with(monkeypatch, live_owner=OWNER)

    assert catalog.begin_delete(OWNER, "doc-1") is True

    joined = "\n".join(connection.statements)
    assert joined.index("INSERT INTO rag_document_tombstones") < joined.index("DELETE FROM rag_documents")
    assert "jsonb_array_elements" in joined
    assert "has_deleted_citations = true" in joined


def test_begin_delete_accepts_same_owner_tombstone_retry(monkeypatch):
    catalog, _ = catalog_with(monkeypatch, tombstone_owner=OWNER)

    assert catalog.begin_delete(OWNER, "doc-1") is True


def test_begin_delete_hides_cross_owner_document(monkeypatch):
    catalog, connection = catalog_with(monkeypatch, live_owner=OTHER_OWNER)

    assert catalog.begin_delete(OWNER, "doc-1") is False
    assert not any("DELETE FROM rag_documents" in sql for sql in connection.statements)


def test_live_document_ids_returns_only_catalog_rows(monkeypatch):
    catalog, _ = catalog_with(monkeypatch, live_ids=["doc-2"])

    assert catalog.live_document_ids(OWNER, ["doc-1", "doc-2"]) == {"doc-2"}


def test_chat_message_defaults_deleted_citation_flag_to_false():
    message = ChatMessage(
        id=uuid4(),
        conversation_id=uuid4(),
        role="assistant",
        content="answer",
        status="completed",
        citations=[],
        created_at=datetime.now(timezone.utc),
    )

    assert message.has_deleted_citations is False


class StoredObject:
    def __init__(self, object_name):
        self.object_name = object_name


class FakeMinio:
    def __init__(self, names):
        self.names = list(names)
        self.list_calls = []
        self.removed = []

    def list_objects(self, bucket, prefix, recursive):
        self.list_calls.append((bucket, prefix, recursive))
        return [StoredObject(name) for name in self.names if name.startswith(prefix)]

    def remove_objects(self, bucket, objects):
        for item in objects:
            self.removed.append(item._name)
            self.names.remove(item._name)
        return []


def test_object_storage_deletes_only_exact_document_prefix():
    expected = f"users/{OWNER}/documents/doc-1/v1/original/a.pdf"
    other = f"users/{OWNER}/documents/doc-10/v1/original/b.pdf"
    client = FakeMinio([expected, other])
    storage = ObjectStorage()
    storage._client = client

    storage.delete_document(OWNER, "doc-1")

    assert client.removed == [expected]
    assert client.list_calls[0] == (
        storage.bucket,
        f"users/{OWNER}/documents/doc-1/",
        True,
    )
    assert storage.document_exists(OWNER, "doc-1") is False


class FakeQdrant:
    def __init__(self, points=None):
        self.points = points or []
        self.selector = None

    def collection_exists(self, _collection):
        return True

    def delete(self, _collection, points_selector, wait):
        self.selector = points_selector
        self.points = []

    def scroll(self, _collection, **_kwargs):
        return self.points[:1], None


def test_vector_store_deletes_all_versions_with_owner_document_filter():
    client = FakeQdrant(points=[object()])
    store = VectorStore.__new__(VectorStore)
    store.client = client

    store.delete_document(OWNER, "doc-1")

    conditions = client.selector.filter.must
    values = {condition.key: condition.match.value for condition in conditions}
    assert values == {"owner_id": str(OWNER), "document_id": "doc-1"}
    assert store.document_exists(OWNER, "doc-1") is False
