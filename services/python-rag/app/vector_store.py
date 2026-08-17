from uuid import uuid5, NAMESPACE_URL
from uuid import UUID
from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, FieldCondition, Filter, MatchValue, PointStruct, VectorParams
from .models import Citation, DocumentChunkDetail, IndexRequest
from .embeddings import BaseEmbedding, OllamaEmbedding
from .settings import settings

COLLECTION = "document_chunks"


class VectorStore:
    def __init__(self, embedding: BaseEmbedding | None = None) -> None:
        self.client = QdrantClient(url=settings.qdrant_url)
        self.embedding = embedding or OllamaEmbedding()

    def ensure_collection(self, dimension: int) -> None:
        if not self.client.collection_exists(COLLECTION):
            self.client.create_collection(COLLECTION, vectors_config=VectorParams(size=dimension, distance=Distance.COSINE))

    async def index(self, request: IndexRequest) -> int:
        if request.owner_id is None:
            raise ValueError("owner_id is required for vector indexing")
        vectors = await self.embedding.embed([chunk.text for chunk in request.chunks])
        self.ensure_collection(len(vectors[0]))
        points = [PointStruct(id=str(uuid5(NAMESPACE_URL, f"{request.document_id}:{request.version}:{i}")), vector=vector, payload={
            "owner_id": str(request.owner_id), "document_id": request.document_id, "document_name": request.document_name, "version": request.version,
            "chunk_index": i, "page": chunk.page, "section": chunk.section, "text": chunk.text,
            "confidence": chunk.confidence, "char_start": chunk.char_start, "char_end": chunk.char_end,
        }) for i, (chunk, vector) in enumerate(zip(request.chunks, vectors))]
        self.client.upsert(COLLECTION, points=points, wait=True)
        return len(points)

    def chunks_for_document(self, document_id: str, owner_id: UUID, version: int | None = None) -> list[DocumentChunkDetail]:
        must = [
            FieldCondition(key="owner_id", match=MatchValue(value=str(owner_id))),
            FieldCondition(key="document_id", match=MatchValue(value=document_id)),
        ]
        if version is not None:
            must.append(FieldCondition(key="version", match=MatchValue(value=version)))
        points, _ = self.client.scroll(
            COLLECTION,
            scroll_filter=Filter(must=must),
            limit=10000,
            with_payload=True,
            with_vectors=False,
        )
        rows = sorted(points, key=lambda point: int(point.payload.get("chunk_index", 0)))
        return [
            DocumentChunkDetail(
                index=int(point.payload.get("chunk_index", index)),
                page=point.payload.get("page"),
                section=point.payload.get("section"),
                text=point.payload["text"],
                char_start=point.payload.get("char_start"),
                char_end=point.payload.get("char_end"),
                confidence=float(point.payload.get("confidence", 1)),
            )
            for index, point in enumerate(rows)
        ]

    async def search(
        self,
        question: str,
        owner_id: UUID,
        document_scope: list[tuple[str, int]] | None = None,
    ) -> list[Citation]:
        if document_scope is not None and not document_scope:
            return []
        vector = (await self.embedding.embed([question]))[0]
        must = [FieldCondition(key="owner_id", match=MatchValue(value=str(owner_id)))]
        query_filter = Filter(
            must=must,
            should=[
                Filter(
                    must=[
                        FieldCondition(key="document_id", match=MatchValue(value=document_id)),
                        FieldCondition(key="version", match=MatchValue(value=version)),
                    ]
                )
                for document_id, version in document_scope
            ] if document_scope is not None else None,
        )
        hits = self.client.query_points(
            COLLECTION,
            query=vector,
            query_filter=query_filter,
            limit=settings.retrieval_top_k,
            score_threshold=settings.retrieval_score_threshold,
        ).points
        return [Citation(document_id=p.payload["document_id"], document_name=p.payload["document_name"], version=p.payload["version"], page=p.payload.get("page"), section=p.payload.get("section"), excerpt=p.payload["text"], confidence=min(1, max(0, p.score))) for p in hits if p.payload.get("confidence", 1) >= .7]
