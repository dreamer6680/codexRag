import asyncio
from types import SimpleNamespace
from uuid import UUID

from app.document_structure import BoundingBox, ChunkEntities
from app.models import ChunkInput, IndexRequest
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


class IndexRecordingClient:
    def collection_exists(self, collection):
        return True

    def upsert(self, collection, points, wait):
        self.points = points


def test_index_persists_structured_chunk_payload():
    store = VectorStore(embedding=StaticEmbedding())
    client = IndexRecordingClient()
    store.client = client
    request = IndexRequest(
        owner_id=OWNER,
        document_id="resume",
        document_name="resume.pdf",
        version=2,
        chunks=[
            ChunkInput(
                text="公司：珠海环届云有限公司\n岗位：全栈研发\n项目：FastGPT",
                page=1,
                chunk_type="resume_experience",
                section_path=["工作经历", "珠海环届云有限公司"],
                parent_context="工作经历 / 珠海环届云有限公司",
                keywords=["珠海环届云有限公司", "全栈研发", "FastGPT"],
                entities=ChunkEntities(
                    companies=["珠海环届云有限公司"], roles=["全栈研发"], projects=["FastGPT"]
                ),
                bbox=BoundingBox(x0=300, y0=100, x1=580, y1=500),
                parser_confidence=0.94,
            )
        ],
    )

    assert asyncio.run(store.index(request)) == 1
    payload = client.points[0].payload
    assert payload["chunk_type"] == "resume_experience"
    assert payload["section_path"] == ["工作经历", "珠海环届云有限公司"]
    assert payload["entities"]["projects"] == ["FastGPT"]
    assert payload["bbox"] == {"x0": 300.0, "y0": 100.0, "x1": 580.0, "y1": 500.0}
    assert payload["parser_confidence"] == 0.94


class ScrollRecordingClient:
    def scroll(self, *args, **kwargs):
        return ([SimpleNamespace(payload={
            "chunk_index": 0,
            "text": "项目：FastGPT",
            "page": 1,
            "section": "工作经历 / 珠海环届云有限公司",
            "chunk_type": "resume_experience",
            "section_path": ["工作经历", "珠海环届云有限公司"],
            "parent_context": "工作经历 / 珠海环届云有限公司",
            "keywords": ["FastGPT"],
            "entities": {"companies": ["珠海环届云有限公司"], "roles": ["全栈研发"], "projects": ["FastGPT"]},
            "bbox": {"x0": 300, "y0": 100, "x1": 580, "y1": 500},
            "parser_confidence": 0.94,
            "confidence": 0.94,
        })], None)


def test_document_chunks_restore_structured_metadata():
    store = VectorStore(embedding=StaticEmbedding())
    store.client = ScrollRecordingClient()

    chunks = store.chunks_for_document("resume", OWNER, 2)

    assert chunks[0].chunk_type == "resume_experience"
    assert chunks[0].entities.roles == ["全栈研发"]
    assert chunks[0].bbox.x0 == 300
    assert chunks[0].parser_confidence == 0.94
