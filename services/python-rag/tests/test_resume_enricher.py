from app.document_structure import DocumentBlock, StructuredDocument
from app.resume_enricher import ResumeEnricher


def resume_document() -> StructuredDocument:
    return StructuredDocument(
        document_id="resume-1",
        name="孟哲全栈简历.pdf",
        parser="pymupdf-layout",
        blocks=[
            DocumentBlock(block_type="heading", text="工作经历", section_path=["工作经历"], heading_level=1),
            DocumentBlock(block_type="paragraph", text="珠海环届云有限公司", section_path=["工作经历"]),
            DocumentBlock(block_type="paragraph", text="全栈研发", section_path=["工作经历"]),
            DocumentBlock(block_type="paragraph", text="FastGPT", section_path=["工作经历"]),
            DocumentBlock(block_type="list_item", text="将 Hugo 文档迁移到 Fumadoc", section_path=["工作经历"]),
            DocumentBlock(block_type="list_item", text="实现 Next.js 长短链系统", section_path=["工作经历"]),
            DocumentBlock(block_type="list_item", text="实现 Redis 定时同步知识库", section_path=["工作经历"]),
            DocumentBlock(block_type="list_item", text="参与客户定制开发和需求沟通", section_path=["工作经历"]),
        ],
    )


def test_enricher_preserves_company_role_project_and_responsibilities():
    experiences = ResumeEnricher().extract(resume_document())

    assert len(experiences) == 1
    experience = experiences[0]
    assert experience.company == "珠海环届云有限公司"
    assert experience.role == "全栈研发"
    assert experience.project == "FastGPT"
    assert experience.responsibilities == [
        "将 Hugo 文档迁移到 Fumadoc",
        "实现 Next.js 长短链系统",
        "实现 Redis 定时同步知识库",
        "参与客户定制开发和需求沟通",
    ]
    assert experience.start_index == 1
    assert experience.end_index == 8


def test_enricher_does_not_invent_missing_role_or_project():
    document = StructuredDocument(
        document_id="resume-2",
        name="resume.md",
        blocks=[
            DocumentBlock(block_type="heading", text="工作经历", section_path=["工作经历"], heading_level=1),
            DocumentBlock(block_type="paragraph", text="某某科技有限公司", section_path=["工作经历"]),
            DocumentBlock(block_type="list_item", text="维护内部知识库", section_path=["工作经历"]),
        ],
    )

    experience = ResumeEnricher().extract(document)[0]

    assert experience.company == "某某科技有限公司"
    assert experience.role is None
    assert experience.project is None

