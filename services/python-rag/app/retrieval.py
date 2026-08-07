"""Vector, MQE, HyDE and hybrid retrieval with reciprocal-rank fusion."""
from .models import Citation
from .ollama import OllamaClient
from .settings import settings
from .vector_store import VectorStore


def _key(citation: Citation) -> tuple[str, int, int | None, str | None, str]:
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
    ) -> None:
        self.store = store or VectorStore()
        self.llm = llm or OllamaClient()

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
        document_ids: list[str] | None = None,
        strategy: str | None = None,
    ) -> list[Citation]:
        selected = strategy or settings.retrieval_strategy
        queries = [question]
        try:
            if selected in {"mqe", "hybrid"}:
                queries.extend(await self._expand(question))
            if selected in {"hyde", "hybrid"}:
                queries.extend(await self._hyde(question))
        except Exception:
            # Query enhancement is optional; base vector retrieval remains available.
            pass

        ranked_lists = [await self.store.search(query, document_ids) for query in queries]
        scores: dict[tuple[str, int, int | None, str | None, str], float] = {}
        items: dict[tuple[str, int, int | None, str | None, str], Citation] = {}
        for ranked in ranked_lists:
            for rank, item in enumerate(ranked):
                key = _key(item)
                scores[key] = scores.get(key, 0.0) + 1.0 / (60 + rank + 1)
                items.setdefault(key, item)
        ordered = sorted(items, key=scores.get, reverse=True)
        return [items[key] for key in ordered[: settings.retrieval_top_k]]
