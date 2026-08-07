"""End-to-end facade for document ingestion and retrieval."""
from .document_processor import DocumentProcessor
from .models import Citation, Document
from .retrieval import MultiStrategyRetriever
from .vector_store import VectorStore


class RAGPipeline:
    def __init__(
        self,
        processor: DocumentProcessor | None = None,
        store: VectorStore | None = None,
        retriever: MultiStrategyRetriever | None = None,
    ) -> None:
        self.processor = processor or DocumentProcessor()
        self.store = store or VectorStore()
        self.retriever = retriever or MultiStrategyRetriever(store=self.store)

    async def ingest(self, document: Document) -> int:
        request = self.processor.to_index_request(document)
        return await self.store.index(request)

    async def retrieve(
        self,
        question: str,
        document_ids: list[str] | None = None,
        strategy: str | None = None,
    ) -> list[Citation]:
        return await self.retriever.retrieve(question, document_ids, strategy)
