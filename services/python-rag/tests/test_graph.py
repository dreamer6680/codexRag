import asyncio

from app.graph import answer, build_graph, evidence_gate, retrieve
from app.models import Citation
from app.settings import settings


def test_no_evidence_always_refuses():
    assert evidence_gate({"question": "不存在的内容", "citations": []}) == "refuse_answer"


def test_graph_compiles_without_state_key_collision():
    assert build_graph() is not None


def test_retrieve_drops_low_relevance_candidates_before_evidence_gate(monkeypatch):
    async def fake_retrieve(self, question, document_scope=None, strategy=None):
        return [
            Citation(
                document_id="doc-1",
                document_name="thesis.pdf",
                version=1,
                excerpt="unrelated thesis content",
                confidence=0.5038,
            )
        ]

    monkeypatch.setattr("app.graph.MultiStrategyRetriever.retrieve", fake_retrieve)

    state = asyncio.run(retrieve({"question": "需求评审需要哪些角色", "document_scope": [("doc-1", 1)]}))

    assert state["citations"] == []
    assert state["confidence"] == "none"
    assert state["reason"] == "low_relevance"


def test_answer_recomputes_confidence_from_citations_that_fit_context(monkeypatch):
    async def fake_choose(self):
        return "chat-model", None

    async def fake_chat(self, model, system, prompt):
        return "answer [1]"

    monkeypatch.setattr("app.graph.OllamaClient.choose_chat_model", fake_choose)
    monkeypatch.setattr("app.graph.OllamaClient.chat", fake_chat)
    monkeypatch.setattr(settings, "context_max_chars", 10)
    state = {
        "question": "question",
        "confidence": "high",
        "citations": [
            Citation(document_id="doc", document_name="doc", version=1, excerpt="weak", confidence=0.55),
            Citation(document_id="doc", document_name="doc", version=1, excerpt="strong", confidence=0.80),
        ],
    }

    result = asyncio.run(answer(state))

    assert len(result["citations"]) == 1
    assert result["confidence"] == "low"
