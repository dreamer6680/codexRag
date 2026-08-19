"""Evidence relevance policy applied before answer generation."""
from dataclasses import dataclass
import re
from typing import Literal

from .models import Citation

ConfidenceLevel = Literal["high", "medium", "low", "none"]


@dataclass(frozen=True)
class EvidenceDecision:
    citations: list[Citation]
    confidence: ConfidenceLevel
    reason: str | None = None


class EvidencePolicy:
    def __init__(
        self,
        min_score: float,
        max_evidence: int,
        medium_score: float = 0.60,
        high_score: float = 0.70,
    ) -> None:
        self.min_score = min_score
        self.max_evidence = max_evidence
        self.medium_score = medium_score
        self.high_score = high_score

    @staticmethod
    def _lexical_overlap(question: str, excerpt: str) -> float:
        normalized_question = re.sub(r"[\W_]+", "", question.lower())
        for phrase in ("请问", "这篇", "是什么", "有哪些", "需要", "哪些", "如何", "为什么", "的"):
            normalized_question = normalized_question.replace(phrase, "")
        normalized_excerpt = re.sub(r"[\W_]+", "", excerpt.lower())
        grams = {
            normalized_question[index : index + 2]
            for index in range(max(0, len(normalized_question) - 1))
        }
        if not grams:
            return 0.0
        return sum(gram in normalized_excerpt for gram in grams) / len(grams)

    def filter(self, citations: list[Citation], question: str = "") -> EvidenceDecision:
        relevant = [item for item in citations if self._is_relevant(item)]
        if question:
            relevant.sort(
                key=lambda item: item.confidence + 0.08 * self._lexical_overlap(question, item.excerpt),
                reverse=True,
            )
        selected = relevant[: self.max_evidence]
        if not selected:
            return EvidenceDecision([], "none", "low_relevance")

        return EvidenceDecision(selected, self.confidence_for(selected))

    def _is_relevant(self, item: Citation) -> bool:
        if item.parser_confidence < 0.7:
            return False
        dense_score = item.dense_score if item.dense_score is not None else item.confidence
        if dense_score >= self.min_score:
            return True
        if item.exact_entity_match and item.relation_coverage:
            return True
        return bool(
            item.relation_coverage
            and item.lexical_score is not None
            and item.lexical_score >= 1.5
        )

    def confidence_for(self, citations: list[Citation]) -> ConfidenceLevel:
        if not citations:
            return "none"
        lowest_score = min(item.confidence for item in citations)
        if lowest_score >= self.high_score:
            confidence: ConfidenceLevel = "high"
        elif lowest_score >= self.medium_score:
            confidence = "medium"
        else:
            confidence = "low"
        return confidence
