"""Evidence-first LangGraph pipeline. Retrieval is intentionally injectable for tests."""
from typing import TypedDict
from langgraph.graph import END, START, StateGraph
from .models import Citation, QueryResponse
from .ollama import OllamaClient
from .context import ContextBuilder
from .evidence import EvidencePolicy
from .retrieval import MultiStrategyRetriever
from .settings import settings


class RAGState(TypedDict, total=False):
    question: str
    document_scope: list[tuple[str, int]]
    citations: list[Citation]
    answer: str
    status: str
    reason: str
    model: str
    strategy: str
    confidence: str


async def retrieve(state: RAGState) -> RAGState:
    # Low-confidence/OCR-uncertain chunks are filtered by the store before evidence gating.
    try:
        candidates = await MultiStrategyRetriever().retrieve(
            state["question"], state.get("document_scope"), state.get("strategy")
        )
        decision = EvidencePolicy(
            min_score=settings.retrieval_min_evidence_score,
            max_evidence=settings.retrieval_max_evidence,
            medium_score=settings.retrieval_medium_confidence_score,
            high_score=settings.retrieval_high_confidence_score,
        ).filter(candidates, question=state["question"])
        return {
            "citations": decision.citations,
            "confidence": decision.confidence,
            "reason": decision.reason,
        }
    except Exception:
        # An unavailable vector database must never cause fabricated output.
        return {"citations": [], "confidence": "none", "reason": "retrieval_unavailable"}


def evidence_gate(state: RAGState) -> str:
    return "generate_answer" if state.get("citations") else "refuse_answer"


async def refuse(state: RAGState) -> RAGState:
    return {
        "status": "refused",
        "answer": "现有知识库中没有足以支持该问题的可靠证据，因此我不能确认答案。",
        "confidence": "none",
        "reason": state.get("reason") or "insufficient_evidence",
    }


async def answer(state: RAGState) -> RAGState:
    client = OllamaClient()
    model, error = await client.choose_chat_model()
    if not model:
        return {"status": "unavailable", "answer": "本地模型当前不可用。", "reason": error or "ollama_unavailable"}
    evidence, citations = ContextBuilder(settings.context_max_chars).build(state["citations"])
    confidence = EvidencePolicy(
        min_score=settings.retrieval_min_evidence_score,
        max_evidence=settings.retrieval_max_evidence,
        medium_score=settings.retrieval_medium_confidence_score,
        high_score=settings.retrieval_high_confidence_score,
    ).confidence_for(citations)
    system = "你是严格的本地知识库助手。只能根据给定证据回答；不能补充外部知识；每项结论都要标记 [编号]。"
    text = await client.chat(model, system, f"问题：{state['question']}\n\n证据：\n{evidence}")
    return {
        "status": "answered",
        "answer": text,
        "citations": citations,
        "confidence": confidence,
        "model": model,
        "reason": error,
    }


def build_graph():
    graph = StateGraph(RAGState)
    graph.add_node("retrieve", retrieve)
    # Node names must not collide with RAGState keys (for example, "answer").
    graph.add_node("generate_answer", answer)
    graph.add_node("refuse_answer", refuse)
    graph.add_edge(START, "retrieve")
    graph.add_conditional_edges(
        "retrieve",
        evidence_gate,
        {
            "generate_answer": "generate_answer",
            "refuse_answer": "refuse_answer",
        },
    )
    graph.add_edge("generate_answer", END)
    graph.add_edge("refuse_answer", END)
    return graph.compile()


async def run_query(
    question: str,
    document_scope: list[tuple[str, int]] | None = None,
    strategy: str | None = None,
) -> QueryResponse:
    result = await build_graph().ainvoke(
        {"question": question, "document_scope": document_scope or [], "strategy": strategy or settings.retrieval_strategy}
    )
    return QueryResponse(
        status=result["status"],
        answer=result["answer"],
        citations=result.get("citations", []),
        confidence=result.get("confidence", "none"),
        model=result.get("model"),
        reason=result.get("reason"),
    )
