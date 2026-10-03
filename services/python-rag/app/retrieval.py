"""Vector, MQE, HyDE and hybrid retrieval with reciprocal-rank fusion."""

from uuid import UUID

from .document_catalog import DocumentCatalog
from .lexical_retriever import LexicalHit, LexicalRetriever
from .models import Citation
from .ollama import OllamaClient
from .settings import settings
from .vector_store import VectorStore
from .structure_chunker import _chunk_id 


class CatalogUnavailableError(RuntimeError):
    """The active document-version scope could not be loaded safely."""


def _key(citation: Citation) -> str:
    """Return the canonical chunk identity used by all retrieval strategies."""
    return citation.chunk_id


class MultiStrategyRetriever:
    def __init__(
        self,
        store: VectorStore | None = None,
        llm: OllamaClient | None = None,
        catalog: DocumentCatalog | None = None,
        lexical: LexicalRetriever | None = None,
    ) -> None:
        self.store = store or VectorStore()
        self.llm = llm or OllamaClient()
        self.catalog = catalog or DocumentCatalog()
        self.lexical = lexical or LexicalRetriever(self.store)

    async def _expand(self, question: str) -> list[str]:
        model, _ = await self.llm.choose_chat_model()

        if not model:
            return []

        prompt = (
            "为下面的问题生成 3 个语义不同、适合知识库检索的中文查询。"
            "每行一个，只输出查询文本。\n"
            f"问题：{question}"
        )

        text = await self.llm.chat(
            model,
            "你是检索查询改写器。",
            prompt,
        )

        return [
            line.strip(" -0123456789.、")
            for line in text.splitlines()
            if line.strip()
        ][:3]

    async def _hyde(self, question: str) -> list[str]:
        model, _ = await self.llm.choose_chat_model()

        if not model:
            return []

        prompt = (
            "写一段可能回答该问题的简短知识库正文，"
            "用于向量检索，不要声称它是真实答案：\n"
            f"{question}"
        )

        text = await self.llm.chat(
            model,
            "你负责生成假设性检索文档。",
            prompt,
        )

        return [text] if text.strip() else []

    async def retrieve(
        self,
        question: str,
        owner_id: UUID,
        document_ids: list[str] | None = None,
        strategy: str | None = None,
    ) -> list[Citation]:
        selected = strategy or settings.retrieval_strategy

        queries = [question]

        # Query enhancement is optional.
        try:
            if selected == "mqe":
                queries.extend(await self._expand(question))

            elif selected == "hyde":
                queries.extend(await self._hyde(question))

        except Exception:
            # Base retrieval remains available even if enhancement fails.
            pass

        # ---------------------------------------------------------
        # 1. Resolve document scope
        # ---------------------------------------------------------
        try:
            document_scope = self.catalog.ready_document_scopes(
                owner_id,
                document_ids,
            )
        except Exception as exc:
            raise CatalogUnavailableError(
                "document catalog unavailable"
            ) from exc

        # ---------------------------------------------------------
        # 2. Dense retrieval
        # ---------------------------------------------------------
        ranked_lists: list[list[Citation]] = []

        for query in queries:
            ranked = await self.store.search(
                query,
                owner_id,
                document_scope,
            )
            ranked_lists.append(ranked)

        # ---------------------------------------------------------
        # 3. Lexical retrieval
        # ---------------------------------------------------------
        lexical_hits: list[LexicalHit] = []

        if selected == "hybrid":
            lexical_hits = self.lexical.search(
                question,
                owner_id,
                document_scope,
            )

        # ---------------------------------------------------------
        # 4. Reciprocal Rank Fusion
        # ---------------------------------------------------------
        scores: dict[str, float] = {}
        items: dict[str, Citation] = {}

        signals: dict[str, dict[str, object]] = {}

        def get_signal(chunk_id: str) -> dict[str, object]:
            return signals.setdefault(
                chunk_id,
                {
                    "dense": 0.0,
                    "lexical": 0.0,
                    "exact": False,
                    "relation": False,
                    "sources": set(),
                },
            )

        # Dense results
        for ranked in ranked_lists:
            for rank, item in enumerate(ranked):
                chunk_id = _key(item)

                # Standard RRF:
                # 1 / (k + rank)
                scores[chunk_id] = scores.get(chunk_id, 0.0) + (
                    1.0 / (60 + rank + 1)
                )

                items.setdefault(chunk_id, item)

                signal = get_signal(chunk_id)

                dense_score = item.dense_score
                if dense_score is None:
                    dense_score = item.confidence

                signal["dense"] = max(
                    float(signal["dense"]),
                    dense_score,
                )

                sources = signal["sources"]
                assert isinstance(sources, set)
                sources.add("dense")

        # Lexical results
        for rank, hit in enumerate(lexical_hits):
            item = self._citation_from_lexical(hit)
            chunk_id = _key(item)

            scores[chunk_id] = scores.get(chunk_id, 0.0) + (
                1.0 / (60 + rank + 1)
            )

            # Prefer dense metadata when the same chunk already exists.
            if chunk_id not in items:
                items[chunk_id] = item

            signal = get_signal(chunk_id)

            signal["lexical"] = max(
                float(signal["lexical"]),
                hit.score,
            )

            signal["exact"] = (
                bool(signal["exact"])
                or hit.exact_entity_match
            )

            signal["relation"] = (
                bool(signal["relation"])
                or hit.relation_coverage
            )

            sources = signal["sources"]
            assert isinstance(sources, set)
            sources.add("lexical")

        # ---------------------------------------------------------
        # 5. Fused ranking
        # ---------------------------------------------------------
        def fused_score(chunk_id: str) -> float:
            signal = signals[chunk_id]

            structural_bonus = (
                0.01
                if signal["exact"] and signal["relation"]
                else 0.0
            )

            agreement_bonus = (
                0.005
                if len(signal["sources"]) > 1
                else 0.0
            )

            return (
                scores[chunk_id]
                + structural_bonus
                + agreement_bonus
            )

        ordered = sorted(
            items,
            key=fused_score,
            reverse=True,
        )

        # ---------------------------------------------------------
        # 6. Build final citations
        # ---------------------------------------------------------
        output: list[Citation] = []

        for chunk_id in ordered[: settings.retrieval_top_k]:
            signal = signals[chunk_id]

            dense = float(signal["dense"])
            lexical_score = float(signal["lexical"])
            exact = bool(signal["exact"])
            relation = bool(signal["relation"])

            # Retrieval confidence.
            quality = dense

            if exact and relation:
                quality = max(
                    quality,
                    0.78
                    if dense >= settings.retrieval_score_threshold
                    else 0.72,
                )
            elif relation and lexical_score >= 1.5:
                quality = max(quality, 0.64)

            output.append(
                items[chunk_id].model_copy(
                    update={
                        "confidence": min(1.0, quality),
                        "dense_score": dense or None,
                        "lexical_score": lexical_score or None,
                        "rrf_score": fused_score(chunk_id),
                        "exact_entity_match": exact,
                        "relation_coverage": relation,
                        "retrieval_sources": sorted(
                            signal["sources"]
                        ),
                    }
                )
            )

        # ---------------------------------------------------------
        # 7. Final live-document validation
        # ---------------------------------------------------------
        try:
            live_ids = self.catalog.live_document_ids(
                owner_id,
                list(
                    dict.fromkeys(
                        item.document_id
                        for item in output
                    )
                ),
            )
        except Exception as exc:
            raise CatalogUnavailableError(
                "document catalog unavailable"
            ) from exc

        return [
            item
            for item in output
            if item.document_id in live_ids
        ]

    @staticmethod
    def _citation_from_lexical(hit: LexicalHit) -> Citation:
        chunk = hit.chunk

        return Citation(
            # IMPORTANT:
            # Must be identical to the ID used by VectorStore.
          chunk_id=_chunk_id(
            chunk.document_id,
            chunk.version,
            chunk.level,
            chunk.chunk_index,
            ),
            parent_chunk_id=chunk.parent_chunk_id,
            document_id=chunk.document_id,
            document_name=chunk.document_name,
            version=chunk.version,
            page=chunk.page,
            section=chunk.section,
            excerpt=chunk.text,
            confidence=0.0,
            chunk_index=chunk.chunk_index,
            chunk_type=chunk.chunk_type,
            entities=chunk.entities,
            parser_confidence=chunk.parser_confidence,
            lexical_score=hit.score,
            exact_entity_match=hit.exact_entity_match,
            relation_coverage=hit.relation_coverage,
            retrieval_sources=["lexical"],
        )