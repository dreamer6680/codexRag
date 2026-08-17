from types import SimpleNamespace
from uuid import UUID

import pytest

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


@pytest.mark.asyncio
async def test_search_always_filters_vectors_by_owner():
    store = VectorStore(embedding=FakeEmbedding())
    store.client = FakeQdrant()

    assert await store.search("question", OWNER) == []

    conditions = store.client.query_filter.must
    assert any(item.key == "owner_id" and item.match.value == str(OWNER) for item in conditions)


@pytest.mark.asyncio
async def test_search_combines_owner_and_selected_documents():
    store = VectorStore(embedding=FakeEmbedding())
    store.client = FakeQdrant()

    await store.search("question", OWNER, ["doc-a", "doc-b"])

    conditions = store.client.query_filter.must
    assert any(item.key == "owner_id" for item in conditions)
    assert any(item.key == "document_id" and item.match.any == ["doc-a", "doc-b"] for item in conditions)
