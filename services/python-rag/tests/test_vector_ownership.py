import asyncio
from types import SimpleNamespace
from uuid import UUID

from app.vector_store import VectorStore


OWNER = UUID("11111111-1111-1111-1111-111111111111")


class FakeEmbedding:
    async def embed(self, _texts):
        return [[0.1, 0.2]]


class FakeQdrant:
    def __init__(self):
        self.query_filter = None

    def query_points(self, _collection, **kwargs):
        self.query_filter = kwargs["query_filter"]
        return SimpleNamespace(points=[])


def test_search_always_filters_vectors_by_owner():
    store = VectorStore(embedding=FakeEmbedding())
    store.client = FakeQdrant()

    assert asyncio.run(store.search("question", OWNER)) == []

    conditions = store.client.query_filter.must
    assert any(item.key == "owner_id" and item.match.value == str(OWNER) for item in conditions)


def test_search_combines_owner_and_active_document_versions():
    store = VectorStore(embedding=FakeEmbedding())
    store.client = FakeQdrant()

    asyncio.run(store.search("question", OWNER, [("doc-a", 2), ("doc-b", 4)]))

    conditions = store.client.query_filter.must
    assert any(item.key == "owner_id" for item in conditions)
    scopes = store.client.query_filter.should
    assert scopes[0].must[0].match.value == "doc-a"
    assert scopes[0].must[1].match.value == 2
