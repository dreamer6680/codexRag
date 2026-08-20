"""Vector, MQE, HyDE and hybrid retrieval with reciprocal-rank fusion."""
from uuid import UUID
from .document_catalog import DocumentCatalog
from .lexical_retriever import LexicalHit, LexicalRetriever
from .models import Citation
from .ollama import OllamaClient
from .settings import settings
from .vector_store import VectorStore


class CatalogUnavailableError(RuntimeError):
    """The active document-version scope could not be loaded safely."""


def _key(citation: Citation) -> tuple[object, ...]:
    if citation.chunk_index is not None:
        return (citation.document_id, citation.version, citation.chunk_index)
    return (
        citation.document_id,
        citation.version,
        citation.page,
        citation.section,
        citation.excerpt,
    )


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
            "每行一个，只输出查询文本。\n问题：" + question
        )
        text = await self.llm.chat(model, "你是检索查询改写器。", prompt)
        return [line.strip(" -0123456789.、") for line in text.splitlines() if line.strip()][:3]

    async def _hyde(self, question: str) -> list[str]:
        model, _ = await self.llm.choose_chat_model()
        if not model:
            return []
        prompt = "写一段可能回答该问题的简短知识库正文，用于向量检索，不要声称它是真实答案：\n" + question
        return [await self.llm.chat(model, "你负责生成假设性检索文档。", prompt)]

    async def retrieve(
        self,
        question: str,
        owner_id: UUID,
        document_ids: list[str] | None = None,
        strategy: str | None = None,
    ) -> list[Citation]:
        selected = strategy or settings.retrieval_strategy
        queries = [question]
        try:
            if selected == "mqe":
                queries.extend(await self._expand(question))
            if selected == "hyde":
                queries.extend(await self._hyde(question))
        except Exception:
            # Query enhancement is optional; base vector retrieval remains available.
            pass

        try:
            document_scope = self.catalog.ready_document_scopes(owner_id, document_ids)
        except Exception as exc:
            raise CatalogUnavailableError("document catalog unavailable") from exc
        ranked_lists = [await self.store.search(query, owner_id, document_scope) for query in queries]
        lexical_hits = self.lexical.search(question, owner_id, document_scope) if selected == "hybrid" else []
        scores: dict[tuple[object, ...], float] = {}
        items: dict[tuple[object, ...], Citation] = {}
        signals: dict[tuple[object, ...], dict[str, object]] = {}
        for ranked in ranked_lists:
            for rank, item in enumerate(ranked):
                key = _key(item)
                scores[key] = scores.get(key, 0.0) + 1.0 / (60 + rank + 1)
                items.setdefault(key, item)
                signal = signals.setdefault(key, {"dense": 0.0, "lexical": 0.0, "exact": False, "relation": False, "sources": set()})
                signal["dense"] = max(float(signal["dense"]), item.dense_score or item.confidence)
                cast_sources = signal["sources"]
                assert isinstance(cast_sources, set)
                cast_sources.add("dense")
        for rank, hit in enumerate(lexical_hits):
            item = self._citation_from_lexical(hit)
            key = _key(item)
            scores[key] = scores.get(key, 0.0) + 1.0 / (60 + rank + 1)
            if key not in items or item.entities.model_dump(exclude_defaults=True):
                items[key] = item
            signal = signals.setdefault(key, {"dense": 0.0, "lexical": 0.0, "exact": False, "relation": False, "sources": set()})
            signal["lexical"] = max(float(signal["lexical"]), hit.score)
            signal["exact"] = bool(signal["exact"]) or hit.exact_entity_match
            signal["relation"] = bool(signal["relation"]) or hit.relation_coverage
            cast_sources = signal["sources"]
            assert isinstance(cast_sources, set)
            cast_sources.add("lexical")

        def fused_score(key: tuple[object, ...]) -> float:
            signal = signals[key]
            structural = 0.01 if signal["exact"] and signal["relation"] else 0.0
            agreement = 0.005 if len(signal["sources"]) > 1 else 0.0
            return scores[key] + structural + agreement

        ordered = sorted(items, key=fused_score, reverse=True)
        output: list[Citation] = []
        for key in ordered[: settings.retrieval_top_k]:
            signal = signals[key]
            dense = float(signal["dense"])
            lexical_score = float(signal["lexical"])
            exact = bool(signal["exact"])
            relation = bool(signal["relation"])
            quality = dense
            if exact and relation:
                quality = max(quality, 0.78 if dense >= settings.retrieval_score_threshold else 0.72)
            elif relation and lexical_score >= 1.5:
                quality = max(quality, 0.64)
            output.append(
                items[key].model_copy(
                    update={
                        "confidence": min(1, quality),
                        "dense_score": dense or None,
                        "lexical_score": lexical_score or None,
                        "rrf_score": fused_score(key),
                        "exact_entity_match": exact,
                        "relation_coverage": relation,
                        "retrieval_sources": sorted(signal["sources"]),
                    }
                )
            )
        try:
            live_ids = self.catalog.live_document_ids(
                owner_id,
                list(dict.fromkeys(item.document_id for item in output)),
            )
        except Exception as exc:
            raise CatalogUnavailableError("document catalog unavailable") from exc
        return [item for item in output if item.document_id in live_ids]

    @staticmethod
    def _citation_from_lexical(hit: LexicalHit) -> Citation:
        chunk = hit.chunk
        return Citation(
            document_id=chunk.document_id,
            document_name=chunk.document_name,
            version=chunk.version,
            page=chunk.page,
            section=chunk.section,
            excerpt=chunk.text,
            confidence=0,
            chunk_index=chunk.chunk_index,
            chunk_type=chunk.chunk_type,
            entities=chunk.entities,
            parser_confidence=chunk.parser_confidence,
            lexical_score=hit.score,
            exact_entity_match=hit.exact_entity_match,
            relation_coverage=hit.relation_coverage,
            retrieval_sources=["lexical"],
        )
