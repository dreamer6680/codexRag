from multiprocessing import Value
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
        if not vectors:
            return 0
        self.ensure_collection(len(vectors[0]))
        points = []
        for index, (chunk, vector) in enumerate(
            zip(request.chunks, vectors)
        ):
            # chunk_id 必须使用 ChunkInput 已经生成好的稳定 ID。
            # 不要在这里重新生成一个不同规则的 ID。
            chunk_id = chunk.chunk_id

            points.append(
                PointStruct(
                    # Qdrant point ID 与业务 chunk_id 保持一致。
                    id=chunk_id,
                    vector=vector,
                    payload={
                        "owner_id": str(request.owner_id),

                        "document_id": request.document_id,
                        "document_name": request.document_name,
                        "version": request.version,

                        # ---- chunk identity ----
                        "chunk_id": chunk_id,
                        "parent_chunk_id": chunk.parent_chunk_id,
                        "level": chunk.level,
                        "chunk_index": index,

                        # ---- content ----
                        "text": chunk.text,

                        # ---- source location ----
                        "page": chunk.page,
                        "section": chunk.section,
                        "char_start": chunk.char_start,
                        "char_end": chunk.char_end,

                        # ---- structure ----
                        "chunk_type": chunk.chunk_type,
                        "section_path": chunk.section_path,
                        "parent_context": chunk.parent_context,

                        # ---- retrieval ----
                        "keywords": chunk.keywords,
                        "entities": chunk.entities.model_dump(),

                        # ---- quality ----
                        "confidence": chunk.confidence,
                        "parser_confidence": chunk.parser_confidence,

                        # ---- geometry ----
                        "bbox": (
                            chunk.bbox.model_dump()
                            if chunk.bbox
                            else None
                        ),
                    },
                )
            )
        self.client.upsert(COLLECTION, points=points, wait=True)
        return len(points)

    def chunks_for_document(
        self,
        document_id: str,
        owner_id: UUID,
        version: int | None = None,
    ) -> list[DocumentChunkDetail]:
        must = [
            FieldCondition(
                key="owner_id",
                match=MatchValue(value=str(owner_id)),
            ),
            FieldCondition(
                key="document_id",
                match=MatchValue(value=document_id),
            ),
        ]

        if version is not None:
            must.append(
                FieldCondition(
                    key="version",
                    match=MatchValue(value=version),
                )
            )

        points, _ = self.client.scroll(
            COLLECTION,
            scroll_filter=Filter(must=must),
            limit=10000,
            with_payload=True,
            with_vectors=False,
        )

        rows = sorted(
            points,
            key=lambda point: int(
                point.payload.get("chunk_index", 0)
            ),
        )

        result: list[DocumentChunkDetail] = []

        for fallback_index, point in enumerate(rows):
            payload = point.payload

            chunk_index = payload.get("chunk_index")

            if chunk_index is None:
                chunk_index = fallback_index

            result.append(
                DocumentChunkDetail(
                    chunk_id=payload["chunk_id"],
                    parent_chunk_id=payload.get("parent_chunk_id"),
                    level=int(payload.get("level", 1)),
                    index=int(chunk_index),
                    page=payload.get("page"),
                    section=payload.get("section"),
                    text=payload["text"],
                    char_start=payload.get("char_start"),
                    char_end=payload.get("char_end"),
                    confidence=float(
                        payload.get("confidence", 1)
                    ),
                    chunk_type=payload.get(
                        "chunk_type",
                        "paragraph",
                    ),
                    section_path=payload.get(
                        "section_path",
                        [],
                    ),
                    parent_context=payload.get(
                        "parent_context"
                    ),
                    keywords=payload.get(
                        "keywords",
                        [],
                    ),
                    entities=payload.get(
                        "entities",
                        {},
                    ),
                    bbox=payload.get("bbox"),
                    parser_confidence=float(
                        payload.get(
                            "parser_confidence",
                            1,
                        )
                    ),
                )
            )

        return result

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
                chunk_id=point.payload["chunk_id"],
                parent_chunk_id=point.payload.get("parent_chunk_id"),
                level=int(point.payload.get("level", 1)),
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
        # 没有限定文档时，允许检索全部文档；
        # 显式传入空 scope 时，直接返回空结果。
        if document_scope is not None and not document_scope:
            return []

        # ---------------------------------------------------------
        # 1. Query embedding
        # ---------------------------------------------------------
        vector = (await self.embedding.embed([question]))[0]

        # ---------------------------------------------------------
        # 2. 只检索 L2
        # ---------------------------------------------------------
        must = [
            FieldCondition(
                key="owner_id",
                match=MatchValue(value=str(owner_id)),
            ),
            FieldCondition(
                key="level",
                match=MatchValue(value=2),
            ),
        ]

        # 如果指定了 document_scope：
        # owner_id AND level=2 AND
        # (
        #     document_id=A AND version=1
        #     OR
        #     document_id=B AND version=2
        # )
        query_filter = Filter(
            must=must,
            should=[
                Filter(
                    must=[
                        FieldCondition(
                            key="document_id",
                            match=MatchValue(value=document_id),
                        ),
                        FieldCondition(
                            key="version",
                            match=MatchValue(value=version),
                        ),
                    ]
                )
                for document_id, version in document_scope
            ]
            if document_scope is not None
            else None,
        )

        # ---------------------------------------------------------
        # 3. Dense retrieval
        # ---------------------------------------------------------
        hits = self.client.query_points(
            COLLECTION,
            query=vector,
            query_filter=query_filter,
            limit=settings.retrieval_top_k,
            score_threshold=settings.retrieval_score_threshold,
        ).points

        if not hits:
            return []

        # ---------------------------------------------------------
        # 4. L2 去重
        #
        # 一个 L1 parent 下面可能有多个 L2：
        #
        #       L1: 教育经历
        #          ├── L2-1
        #          └── L2-2
        #
        # 如果问题同时命中 L2-1 / L2-2，
        # 我们最终只需要这个 parent。
        #
        # 注意：
        # 不能简单地 seen.add(parent_id) 后保留第一个，
        # 因为 Qdrant 返回的是按 score 排序的，但这里显式
        # 保留最高分的 L2 更安全。
        # ---------------------------------------------------------
        best_l2_by_parent: dict[str, object] = {}

        for hit in hits:
            payload = hit.payload or {}

            parent_id = payload.get("parent_chunk_id")

            # L2 必须存在 parent。
            if not parent_id:
                continue

            previous = best_l2_by_parent.get(parent_id)

            if previous is None or float(hit.score) > float(previous.score):
                best_l2_by_parent[parent_id] = hit

        if not best_l2_by_parent:
            return []

        # 保持按照 L2 检索分数排序。
        hits = sorted(
            best_l2_by_parent.values(),
            key=lambda hit: float(hit.score),
            reverse=True,
        )

        # ---------------------------------------------------------
        # 5. 根据 L2 找对应的 L1 parent
        # ---------------------------------------------------------
        parent_ids = list(best_l2_by_parent.keys())

        parent_filter = Filter(
            must=[
                FieldCondition(
                    key="owner_id",
                    match=MatchValue(value=str(owner_id)),
                ),
                FieldCondition(
                    key="level",
                    match=MatchValue(value=1),
                ),
            ],
            should=[
                FieldCondition(
                    key="chunk_id",
                    match=MatchValue(value=parent_id),
                )
                for parent_id in parent_ids
            ],
        )

        parent_points, _ = self.client.scroll(
            COLLECTION,
            scroll_filter=parent_filter,
            limit=len(parent_ids),
            with_payload=True,
            with_vectors=False,
        )

        if not parent_points:
            return []

        # ---------------------------------------------------------
        # 6. 建立 parent_id -> parent point 映射
        # ---------------------------------------------------------
        parents = {
            point.payload["chunk_id"]: point
            for point in parent_points
            if point.payload and point.payload.get("chunk_id")
        }

        # ---------------------------------------------------------
        # 7. 最终只返回 L1
        # ---------------------------------------------------------
        results: list[Citation] = []

        for hit in hits:
            payload = hit.payload or {}

            parent_id = payload.get("parent_chunk_id")

            if not parent_id:
                continue

            parent = parents.get(parent_id)

            if parent is None:
                continue

            parent_payload = parent.payload or {}

            # L2 的 confidence 作为本次检索证据质量判断。
            score = float(hit.score)

            if score < settings.retrieval_min_evidence_score:
                continue

            # -----------------------------------------------------
            # 这里非常重要：
            #
            # Citation 返回的是 L1。
            #
            # chunk_id       -> L1 chunk_id
            # parent_chunk_id -> None
            # excerpt        -> L1 完整内容
            #
            # 但是 confidence / dense_score
            # 使用的是命中的 L2 score。
            #
            # 这样：
            #   检索依据 = L2
            #   LLM上下文 = L1
            # -----------------------------------------------------
            results.append(
                Citation(
                    chunk_id=parent_payload["chunk_id"],
                    parent_chunk_id=None,

                    document_id=parent_payload["document_id"],
                    document_name=parent_payload["document_name"],
                    version=int(parent_payload["version"]),

                    page=parent_payload.get("page"),
                    section=parent_payload.get("section"),

                    # 给 LLM 的内容是 L1
                    excerpt=parent_payload["text"],

                    # 检索分数来自命中的 L2
                    confidence=min(
                        1.0,
                        max(0.0, float(hit.score)),
                    ),

                    chunk_index=parent_payload.get("chunk_index"),
                    chunk_type=parent_payload.get("chunk_type"),

                    entities=parent_payload.get("entities", {}),

                    parser_confidence=float(
                        parent_payload.get(
                            "parser_confidence",
                            1.0,
                        )
                    ),

                    dense_score=min(
                        1.0,
                        max(0.0, float(hit.score)),
                    ),

                    retrieval_sources=["dense"],
                )
            )

        return results