"""Owner-scoped BM25 retrieval with generic exact-match signals."""

from collections import Counter
from dataclasses import dataclass
from math import log
from uuid import UUID

from .models import StoredChunk
from .query_analysis import (
    QueryAnalysis,
    analyze_query,
    tokenize_text,
)


@dataclass(frozen=True)
class LexicalHit:
    chunk: StoredChunk
    score: float
    exact_entity_match: bool
    relation_coverage: bool


def _entity_phrases(chunk: StoredChunk) -> list[str]:
    """Return all structured entity phrases attached to a chunk."""
    return (
        chunk.entities.companies
        + chunk.entities.roles
        + chunk.entities.projects
        + chunk.entities.dates
        + chunk.entities.people
    )


def _relation_coverage(
    analysis: QueryAnalysis,
    chunk: StoredChunk,
) -> bool:
    """
    Generic relation coverage.

    We deliberately avoid document-type-specific rules such as:
        "岗位："
        "职责："
        chunk_type == "resume_experience"

    Instead, relation coverage checks whether the chunk contains the
    semantic evidence required by the query.
    """
    if not analysis.relations:
        return False

    text = chunk.text.lower()

    relation_keywords = {
        "definition": (
            "定义",
            "是指",
            "指的是",
            "概念",
            "含义",
            "是什么",
        ),
        "reason": (
            "原因",
            "由于",
            "因为",
            "原理",
            "目的",
        ),
        "method": (
            "步骤",
            "流程",
            "方法",
            "实现",
            "通过",
            "使用",
        ),
        "comparison": (
            "区别",
            "不同",
            "比较",
            "对比",
            "优点",
            "缺点",
        ),
        "summary": (
            "总结",
            "概括",
            "主要",
            "核心",
            "内容",
        ),
        "time": (
            "年",
            "月",
            "日期",
            "时间",
            "期间",
        ),
        "location": (
            "地点",
            "地址",
            "位置",
            "位于",
            "地区",
        ),
        "person": (
            "作者",
            "负责人",
            "人物",
            "姓名",
        ),
        "quantity": (
            "数量",
            "比例",
            "占比",
            "总数",
            "个",
            "项",
        ),
    }

    covered = 0

    for relation in analysis.relations:
        keywords = relation_keywords.get(relation, ())
        if any(keyword in text for keyword in keywords):
            covered += 1
            continue

        # Structured metadata can also provide relation evidence.
        if relation == "person" and chunk.entities.people:
            covered += 1
        elif relation == "time" and chunk.entities.dates:
            covered += 1
        elif relation == "location":
            if any(
                keyword in text
                for keyword in ("杭州", "北京", "上海", "深圳", "浙江")
            ):
                covered += 1

    return covered == len(analysis.relations)


class LexicalRetriever:
    def __init__(self, store) -> None:
        self.store = store

    def search(
        self,
        question: str,
        owner_id: UUID,
        document_scope: list[tuple[str, int]] | None,
        limit: int = 20,
    ) -> list[LexicalHit]:
        if document_scope is not None and not document_scope:
            return []

        chunks: list[StoredChunk] = self.store.scan_chunks(
            owner_id,
            document_scope,
        )

        if not chunks:
            return []

        analysis = analyze_query(question)

        # ------------------------------------------------------------------
        # Build lexical documents
        # ------------------------------------------------------------------

        documents = [
            tokenize_text(
                chunk.text,
                keywords=chunk.keywords,
                entity_phrases=_entity_phrases(chunk),
            )
            for chunk in chunks
        ]

        document_frequency = Counter(
            token
            for tokens in documents
            for token in set(tokens)
        )

        average_length = (
            sum(len(tokens) for tokens in documents)
            / max(1, len(documents))
        )

        total = len(documents)

        hits: list[LexicalHit] = []

        # ------------------------------------------------------------------
        # BM25
        # ------------------------------------------------------------------

        for chunk, tokens in zip(chunks, documents):
            frequencies = Counter(tokens)

            score = 0.0

            for token in analysis.tokens:
                frequency = frequencies[token]

                if not frequency:
                    continue

                df = document_frequency[token]

                inverse_frequency = log(
                    1
                    + (total - df + 0.5)
                    / (df + 0.5)
                )

                denominator = frequency + 1.2 * (
                    1
                    - 0.75
                    + 0.75 * len(tokens) / max(1, average_length)
                )

                score += (
                    inverse_frequency
                    * frequency
                    * 2.2
                    / denominator
                )

            # ------------------------------------------------------------------
            # Exact phrase/entity signal
            # ------------------------------------------------------------------

            normalized_text = chunk.text.lower()

            entity_values = {
                value.strip().lower()
                for value in _entity_phrases(chunk)
                if value.strip()
            }

            exact = False

            for term in analysis.exact_terms:
                normalized_term = term.strip().lower()

                if not normalized_term:
                    continue

                # Structured entity match.
                if normalized_term in entity_values:
                    exact = True
                    break

                # Phrase match in text.
                if len(normalized_term) >= 3:
                    if normalized_term in normalized_text:
                        exact = True
                        break

            # ------------------------------------------------------------------
            # Generic relation signal
            # ------------------------------------------------------------------

            relation = _relation_coverage(
                analysis,
                chunk,
            )

            if exact:
                score += 3.0

            if relation and analysis.relations:
                score += 1.0

            if score <= 0:
                continue

            hits.append(
                LexicalHit(
                    chunk=chunk,
                    score=score,
                    exact_entity_match=exact,
                    relation_coverage=relation,
                )
            )

        # Exact/entity match > relation coverage > lexical score.
        hits.sort(
            key=lambda hit: (
                hit.exact_entity_match,
                hit.relation_coverage,
                hit.score,
            ),
            reverse=True,
        )

        return hits[:limit]