import asyncio
from uuid import UUID

from app.document_structure import ChunkEntities
from app.evidence import EvidencePolicy
from app.models import Citation, StoredChunk
from app.retrieval import MultiStrategyRetriever


OWNER = UUID("11111111-1111-1111-1111-111111111111")


class StaticCatalog:
    def ready_document_scopes(self, owner_id, document_ids=None):
        assert owner_id == OWNER
        return [("resume", 1), ("thesis", 1)]


class HybridStore:
    async def search(self, question, owner_id, document_scope):
        return [
            Citation(
                document_id="resume",
                document_name="resume.pdf",
                version=1,
                chunk_index=0,
                excerpt="公司：珠海环届云有限公司\n岗位：全栈研发\n项目：FastGPT\n职责：维护知识库",
                confidence=0.4313,
                dense_score=0.4313,
                chunk_type="resume_experience",
                entities=ChunkEntities(
                    companies=["珠海环届云有限公司"], roles=["全栈研发"], projects=["FastGPT"]
                ),
                parser_confidence=0.95,
            ),
            Citation(
                document_id="thesis",
                document_name="thesis.pdf",
                version=1,
                chunk_index=0,
                excerpt="毕业论文题目：智能旅游规划助手设计与实现",
                confidence=0.40,
                dense_score=0.40,
            ),
        ]

    def scan_chunks(self, owner_id, document_scope):
        return [
            StoredChunk(
                document_id="resume",
                document_name="resume.pdf",
                version=1,
                chunk_index=0,
                text="公司：珠海环届云有限公司\n岗位：全栈研发\n项目：FastGPT\n职责：维护知识库",
                chunk_type="resume_experience",
                keywords=["FastGPT", "全栈研发", "珠海环届云有限公司"],
                entities=ChunkEntities(
                    companies=["珠海环届云有限公司"], roles=["全栈研发"], projects=["FastGPT"]
                ),
                parser_confidence=0.95,
            ),
            StoredChunk(
                document_id="thesis",
                document_name="thesis.pdf",
                version=1,
                chunk_index=0,
                text="毕业论文题目：智能旅游规划助手设计与实现",
            ),
        ]


def test_hybrid_fusion_rescues_exact_fastgpt_relationship_below_dense_threshold():
    retriever = MultiStrategyRetriever(store=HybridStore(), catalog=StaticCatalog())

    citations = asyncio.run(retriever.retrieve("在FastGPT负责什么岗位", OWNER, strategy="hybrid"))

    assert citations[0].document_id == "resume"
    assert citations[0].dense_score == 0.4313
    assert citations[0].lexical_score > 0
    assert citations[0].exact_entity_match is True
    assert citations[0].relation_coverage is True
    decision = EvidencePolicy(min_score=0.52, max_evidence=6).filter(
        citations, question="在FastGPT负责什么岗位"
    )
    assert decision.citations[0].document_id == "resume"


def test_unrelated_requirement_review_question_stays_below_evidence_gate():
    retriever = MultiStrategyRetriever(store=HybridStore(), catalog=StaticCatalog())

    citations = asyncio.run(retriever.retrieve("新版本需求评审需要哪些关键角色", OWNER, strategy="hybrid"))
    decision = EvidencePolicy(min_score=0.52, max_evidence=6).filter(citations)

    assert decision.citations == []
    assert decision.reason == "low_relevance"

