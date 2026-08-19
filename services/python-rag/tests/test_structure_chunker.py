from app.resume_enricher import ResumeEnricher
from app.structure_chunker import StructureAwareChunker
from test_resume_enricher import resume_document


def test_resume_experience_is_one_semantic_chunk_when_it_fits():
    chunks = StructureAwareChunker(max_chars=1000).chunk(resume_document())

    assert len(chunks) == 1
    chunk = chunks[0]
    assert chunk.chunk_type == "resume_experience"
    assert "公司：珠海环届云有限公司" in chunk.text
    assert "岗位：全栈研发" in chunk.text
    assert "项目：FastGPT" in chunk.text
    assert "- 实现 Redis 定时同步知识库" in chunk.text
    assert chunk.entities.companies == ["珠海环届云有限公司"]
    assert chunk.entities.roles == ["全栈研发"]
    assert chunk.entities.projects == ["FastGPT"]
    assert "FastGPT" in chunk.keywords


def test_oversized_experience_splits_only_between_responsibilities_and_repeats_context():
    chunks = StructureAwareChunker(max_chars=95).chunk(resume_document())

    assert len(chunks) >= 2
    for chunk in chunks:
        assert chunk.text.startswith(
            "工作经历\n公司：珠海环届云有限公司\n岗位：全栈研发\n项目：FastGPT\n职责："
        )
        assert chunk.entities.projects == ["FastGPT"]
        assert chunk.parent_context == "工作经历 / 珠海环届云有限公司"
    all_text = "\n".join(chunk.text for chunk in chunks)
    for responsibility in ResumeEnricher().extract(resume_document())[0].responsibilities:
        assert f"- {responsibility}" in all_text


def test_non_resume_blocks_keep_atomic_list_boundaries():
    document = resume_document().model_copy(
        update={
            "blocks": [
                resume_document().blocks[0].model_copy(update={"text": "技能", "section_path": ["技能"]}),
                resume_document().blocks[4].model_copy(update={"section_path": ["技能"]}),
                resume_document().blocks[5].model_copy(update={"section_path": ["技能"]}),
            ]
        }
    )

    chunks = StructureAwareChunker(max_chars=20).chunk(document)

    assert [chunk.text for chunk in chunks] == ["将 Hugo 文档迁移到 Fumadoc", "实现 Next.js 长短链系统"]
    assert all(chunk.chunk_type == "list_item" for chunk in chunks)
