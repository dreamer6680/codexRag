import asyncio

from app.vector_store import VectorStore


class FailingEmbedding:
    async def embed(self, texts):
        raise AssertionError("empty document scope must return before embedding or querying")


def test_empty_document_scope_returns_no_results_without_querying_qdrant():
    store = VectorStore(embedding=FailingEmbedding())

    results = asyncio.run(store.search("question", document_ids=[]))

    assert results == []
