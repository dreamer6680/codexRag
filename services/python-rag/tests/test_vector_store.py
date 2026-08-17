import asyncio
from types import SimpleNamespace
from uuid import UUID

from app.vector_store import VectorStore

OWNER = UUID("11111111-1111-1111-1111-111111111111")


class FailingEmbedding:
    async def embed(self, texts):
        raise AssertionError("empty document scope must return before embedding or querying")


def test_empty_document_scope_returns_no_results_without_querying_qdrant():
    store = VectorStore(embedding=FailingEmbedding())

    results = asyncio.run(store.search("question", OWNER, document_scope=[]))

    assert results == []


class StaticEmbedding:
    async def embed(self, texts):
        return [[0.1, 0.2]]


class RecordingClient:
    def query_points(self, *args, **kwargs):
        self.query_filter = kwargs["query_filter"]
        return SimpleNamespace(points=[])


def test_document_scope_filters_by_exact_document_and_version_pair():
    store = VectorStore(embedding=StaticEmbedding())
    client = RecordingClient()
    store.client = client

    asyncio.run(store.search("question", OWNER, document_scope=[("doc-1", 2)]))

    payload = client.query_filter.model_dump(exclude_none=True)
    assert payload["must"][0] == {"key": "owner_id", "match": {"value": str(OWNER)}}
    conditions = payload["should"][0]["must"]
    assert conditions[0] == {"key": "document_id", "match": {"value": "doc-1"}}
    assert conditions[1] == {"key": "version", "match": {"value": 2}}
