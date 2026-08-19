from uuid import UUID

from app.document_structure import ChunkEntities
from app.lexical_retriever import LexicalRetriever
from app.models import StoredChunk


OWNER = UUID("11111111-1111-1111-1111-111111111111")


class StaticChunkStore:
    def __init__(self, chunks):
        self.chunks = chunks
        self.scope = None

    def scan_chunks(self, owner_id, document_scope):
        self.scope = (owner_id, document_scope)
        return self.chunks


def chunk(document_id, text, *, keywords=None, entities=None, chunk_type="paragraph"):
    return StoredChunk(
        document_id=document_id,
        document_name=f"{document_id}.pdf",
        version=1,
        chunk_index=0,
        text=text,
        keywords=keywords or [],
        entities=entities or ChunkEntities(),
        chunk_type=chunk_type,
        parser_confidence=0.95,
    )


def test_bm25_and_exact_entity_rank_fastgpt_work_experience_first():
    store = StaticChunkStore([
        chunk("thesis", "论文题目：智能旅游规划助手设计与实现"),
        chunk("score", "全国大学英语四级考试成绩报告单"),
        chunk(
            "resume",
            "公司：珠海环届云有限公司\n岗位：全栈研发\n项目：FastGPT\n职责：维护知识库",
            keywords=["FastGPT", "全栈研发", "珠海环届云有限公司"],
            entities=ChunkEntities(
                companies=["珠海环届云有限公司"], roles=["全栈研发"], projects=["FastGPT"]
            ),
            chunk_type="resume_experience",
        ),
    ])

    hits = LexicalRetriever(store).search(
        "在FastGPT负责什么岗位", OWNER, [("resume", 1), ("thesis", 1), ("score", 1)]
    )

    assert hits[0].chunk.document_id == "resume"
    assert hits[0].exact_entity_match is True
    assert hits[0].relation_coverage is True
    assert hits[0].score > 0
    assert store.scope == (OWNER, [("resume", 1), ("thesis", 1), ("score", 1)])


def test_company_query_ranks_matching_responsibilities():
    store = StaticChunkStore([
        chunk("other", "某某公司负责通用测试工作"),
        chunk(
            "resume",
            "公司：珠海环届云有限公司\n岗位：全栈研发\n职责：实现 Redis 定时同步知识库",
            entities=ChunkEntities(companies=["珠海环届云有限公司"], roles=["全栈研发"]),
            chunk_type="resume_experience",
        ),
    ])

    hits = LexicalRetriever(store).search(
        "在珠海环届云有限公司负责什么", OWNER, [("resume", 1), ("other", 1)]
    )

    assert hits[0].chunk.document_id == "resume"
    assert hits[0].exact_entity_match is True
    assert hits[0].relation_coverage is True


def test_empty_scope_returns_without_scanning_store():
    class FailingStore:
        def scan_chunks(self, owner_id, document_scope):
            raise AssertionError("empty scope must not access Qdrant")

    assert LexicalRetriever(FailingStore()).search("FastGPT", OWNER, []) == []
