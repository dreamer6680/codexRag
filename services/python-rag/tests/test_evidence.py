from app.evidence import EvidencePolicy
from app.models import Citation


def citation(score: float, text: str) -> Citation:
    return Citation(
        document_id="doc-1",
        document_name="document.pdf",
        version=1,
        excerpt=text,
        confidence=score,
    )


def test_rejects_candidates_when_best_similarity_is_below_minimum():
    decision = EvidencePolicy(min_score=0.52, max_evidence=6).filter(
        [citation(0.5038, "generic requirements text"), citation(0.49, "other text")]
    )

    assert decision.citations == []
    assert decision.confidence == "none"
    assert decision.reason == "low_relevance"


def test_keeps_only_relevant_candidates_and_caps_final_evidence():
    candidates = [citation(0.70 - index * 0.01, f"evidence {index}") for index in range(10)]

    decision = EvidencePolicy(min_score=0.52, max_evidence=6).filter(candidates)

    assert len(decision.citations) == 6
    assert all(item.confidence >= 0.52 for item in decision.citations)
    assert decision.confidence == "high"
    assert decision.reason is None


def test_reports_low_confidence_for_barely_relevant_evidence():
    decision = EvidencePolicy(min_score=0.52, max_evidence=6).filter(
        [citation(0.56, "direct but weak evidence")]
    )

    assert len(decision.citations) == 1
    assert decision.confidence == "low"


def test_exact_question_terms_break_close_vector_score_ties():
    abstract = citation(0.5674, "毕业论文关键词：智能旅游规划、向量语义检索、Workflow")
    title_page = citation(0.5632, "本科毕业设计（论文） 题 目：智能旅游规划助手设计与实现")

    decision = EvidencePolicy(min_score=0.52, max_evidence=6).filter(
        [abstract, title_page], question="这篇毕业论文的题目是什么？"
    )

    assert decision.citations[0] == title_page
