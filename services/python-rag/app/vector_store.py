from uuid import uuid5, NAMESPACE_URL
from uuid import UUID
from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, FieldCondition, Filter, FilterSelector, MatchValue, PointStruct, VectorParams
from .models import Citation, DocumentChunkDetail, IndexRequest, StoredChunk
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
            "chunk_type": chunk.chunk_type, "section_path": chunk.section_path,
            "parent_context": chunk.parent_context, "keywords": chunk.keywords,
            "entities": chunk.entities.model_dump(),
            "bbox": chunk.bbox.model_dump() if chunk.bbox else None,
            "parser_confidence": chunk.parser_confidence,
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
                chunk_type=point.payload.get("chunk_type", "paragraph"),
                section_path=point.payload.get("section_path", []),
                parent_context=point.payload.get("parent_context"),
                keywords=point.payload.get("keywords", []),
                entities=point.payload.get("entities", {}),
                bbox=point.payload.get("bbox"),
                parser_confidence=float(point.payload.get("parser_confidence", 1)),
            )
            for index, point in enumerate(rows)
        ]

    def scan_chunks(
        self,
        owner_id: UUID,
        document_scope: list[tuple[str, int]] | None = None,
    ) -> list[StoredChunk]:
        if document_scope is not None and not document_scope:
            return []
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
        points, _ = self.client.scroll(
            COLLECTION,
            scroll_filter=query_filter,
            limit=10000,
            with_payload=True,
            with_vectors=False,
        )
        return [
            StoredChunk(
                document_id=point.payload["document_id"],
                document_name=point.payload["document_name"],
                version=int(point.payload["version"]),
                chunk_index=int(point.payload.get("chunk_index", 0)),
                text=point.payload["text"],
                page=point.payload.get("page"),
                section=point.payload.get("section"),
                confidence=float(point.payload.get("confidence", 1)),
                chunk_type=point.payload.get("chunk_type", "paragraph"),
                section_path=point.payload.get("section_path", []),
                parent_context=point.payload.get("parent_context"),
                keywords=point.payload.get("keywords", []),
                entities=point.payload.get("entities", {}),
                bbox=point.payload.get("bbox"),
                parser_confidence=float(point.payload.get("parser_confidence", 1)),
            )
            for point in points
            if float(point.payload.get("confidence", 1)) >= 0.7
        ]

    def delete_document_version(self, owner_id: UUID, document_id: str, version: int) -> None:
        self.client.delete(
            COLLECTION,
            points_selector=FilterSelector(
                filter=Filter(
                    must=[
                        FieldCondition(key="owner_id", match=MatchValue(value=str(owner_id))),
                        FieldCondition(key="document_id", match=MatchValue(value=document_id)),
                        FieldCondition(key="version", match=MatchValue(value=version)),
                    ]
                )
            ),
            wait=True,
        )

    @staticmethod
    def _document_filter(owner_id: UUID, document_id: str) -> Filter:
        return Filter(
            must=[
                FieldCondition(key="owner_id", match=MatchValue(value=str(owner_id))),
                FieldCondition(key="document_id", match=MatchValue(value=document_id)),
            ]
        )

    def delete_document(self, owner_id: UUID, document_id: str) -> None:
        if not self.client.collection_exists(COLLECTION):
            return
        self.client.delete(
            COLLECTION,
            points_selector=FilterSelector(filter=self._document_filter(owner_id, document_id)),
            wait=True,
        )

    def document_exists(self, owner_id: UUID, document_id: str) -> bool:
        if not self.client.collection_exists(COLLECTION):
            return False
        points, _ = self.client.scroll(
            COLLECTION,
            scroll_filter=self._document_filter(owner_id, document_id),
            limit=1,
            with_payload=False,
            with_vectors=False,
        )
        return bool(points)

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
        return [
            Citation(
                document_id=p.payload["document_id"],
                document_name=p.payload["document_name"],
                version=p.payload["version"],
                page=p.payload.get("page"),
                section=p.payload.get("section"),
                excerpt=p.payload["text"],
                confidence=min(1, max(0, p.score)),
                chunk_index=p.payload.get("chunk_index"),
                chunk_type=p.payload.get("chunk_type"),
                entities=p.payload.get("entities", {}),
                parser_confidence=float(p.payload.get("parser_confidence", 1)),
                dense_score=min(1, max(0, p.score)),
                retrieval_sources=["dense"],
            )
            for p in hits
            if p.payload.get("confidence", 1) >= .7
        ]
