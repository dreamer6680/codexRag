import asyncio

from app.graph import build_graph, evidence_gate, retrieve
from app.models import Citation


def test_no_evidence_always_refuses():
    assert evidence_gate({"question": "不存在的内容", "citations": []}) == "refuse_answer"


def test_graph_compiles_without_state_key_collision():
    assert build_graph() is not None


def test_retrieve_drops_low_relevance_candidates_before_evidence_gate(monkeypatch):
    async def fake_retrieve(self, question, document_ids=None, strategy=None):
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

    state = asyncio.run(retrieve({"question": "需求评审需要哪些角色", "document_ids": ["doc-1"]}))

    assert state["citations"] == []
    assert state["confidence"] == "none"
    assert state["reason"] == "low_relevance"
