"""Owner-scoped BM25 retrieval with exact entity and relation signals."""
from dataclasses import dataclass
from math import log
from collections import Counter
from uuid import UUID

from .models import StoredChunk
from .query_analysis import QueryAnalysis, analyze_query, tokenize_text


@dataclass(frozen=True)
class LexicalHit:
    chunk: StoredChunk
    score: float
    exact_entity_match: bool
    relation_coverage: bool


def _entity_phrases(chunk: StoredChunk) -> list[str]:
    return (
        chunk.entities.companies
        + chunk.entities.roles
        + chunk.entities.projects
        + chunk.entities.dates
        + chunk.entities.people
    )


def _relation_coverage(analysis: QueryAnalysis, chunk: StoredChunk) -> bool:
    if not analysis.relations:
        return True
    checks = {
        "position": bool(chunk.entities.roles) or "岗位：" in chunk.text or "职位：" in chunk.text,
        "responsibilities": "职责：" in chunk.text or chunk.chunk_type == "resume_experience",
        "title": "题目" in chunk.text or "标题" in chunk.text,
    }
    return all(checks.get(relation, False) for relation in analysis.relations)


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
        chunks: list[StoredChunk] = self.store.scan_chunks(owner_id, document_scope)
        if not chunks:
            return []
        analysis = analyze_query(question)
        documents = [
            tokenize_text(chunk.text, keywords=chunk.keywords, entity_phrases=_entity_phrases(chunk))
            for chunk in chunks
        ]
        document_frequency = Counter(token for tokens in documents for token in set(tokens))
        average_length = sum(len(tokens) for tokens in documents) / max(1, len(documents))
        total = len(documents)
        hits: list[LexicalHit] = []
        for chunk, tokens in zip(chunks, documents):
            frequencies = Counter(tokens)
            score = 0.0
            for token in analysis.tokens:
                frequency = frequencies[token]
                if not frequency:
                    continue
                df = document_frequency[token]
                inverse_frequency = log(1 + (total - df + 0.5) / (df + 0.5))
                denominator = frequency + 1.2 * (
                    1 - 0.75 + 0.75 * len(tokens) / max(1, average_length)
                )
                score += inverse_frequency * frequency * 2.2 / denominator

            normalized_text = chunk.text.lower()
            entities = {value.lower() for value in _entity_phrases(chunk)}
            exact = any(
                term in entities or term in normalized_text
                for term in analysis.exact_terms
            )
            relation = _relation_coverage(analysis, chunk)
            if exact:
                score += 3.0
            if relation and analysis.relations:
                score += 1.0
            if score > 0:
                hits.append(LexicalHit(chunk, score, exact, relation))
        hits.sort(
            key=lambda hit: (hit.exact_entity_match, hit.relation_coverage, hit.score),
            reverse=True,
        )
        return hits[:limit]

