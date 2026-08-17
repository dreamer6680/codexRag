import asyncio
from uuid import UUID

from app.graph import answer, build_graph, evidence_gate, retrieve
from app.models import Citation
from app.settings import settings

OWNER = UUID("11111111-1111-1111-1111-111111111111")


def test_no_evidence_always_refuses():
    assert evidence_gate({"question": "不存在的内容", "citations": []}) == "refuse_answer"


def test_graph_compiles_without_state_key_collision():
    assert build_graph() is not None


def test_retrieve_drops_low_relevance_candidates_before_evidence_gate(monkeypatch):
    async def fake_retrieve(self, question, owner_id, document_ids=None, strategy=None):
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

    state = asyncio.run(retrieve({"question": "需求评审需要哪些角色", "owner_id": OWNER, "document_ids": ["doc-1"]}))

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
    monkeypatch.setattr(settings, "context_max_chars", 2000)
    state = {
        "question": "question",
        "confidence": "high",
        "citations": [
            Citation(document_id="doc", document_name="doc", version=1, excerpt="weak " * 300, confidence=0.55),
            Citation(document_id="doc", document_name="doc", version=1, excerpt="strong " * 300, confidence=0.80),
        ],
    }

    result = asyncio.run(answer(state))

    assert len(result["citations"]) == 1
    assert result["confidence"] == "low"


def test_answer_refuses_if_context_builder_drops_every_citation(monkeypatch):
    async def must_not_choose_model(self):
        raise AssertionError("empty final context must refuse before model selection")

    monkeypatch.setattr("app.graph.OllamaClient.choose_chat_model", must_not_choose_model)
    state = {
        "question": "question",
        "confidence": "high",
        "citations": [
            Citation(document_id="doc", document_name="doc", version=1, excerpt="   ", confidence=0.80),
        ],
    }

    result = asyncio.run(answer(state))

    assert result["status"] == "refused"
    assert result["citations"] == []
    assert result["confidence"] == "none"
    assert result["reason"] == "empty_context"
