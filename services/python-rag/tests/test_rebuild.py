import asyncio
from uuid import UUID

from app.ingestion import IndexRebuilder, IngestionResult
from app.document_structure import DocumentBlock, StructuredDocument
from app.models import ChunkInput, DocumentRecord, IndexRequest


OWNER = UUID("11111111-1111-1111-1111-111111111111")


def record(document_id: str, version: int = 1) -> DocumentRecord:
    return DocumentRecord(
        owner_id=OWNER,
        document_id=document_id,
        document_name=f"{document_id}.md",
        version=version,
        content_type="text/markdown",
        parser="old-parser",
        chunk_count=1,
        original_object_key=f"users/{OWNER}/documents/{document_id}/v{version}/original/{document_id}.md",
        markdown_object_key=f"users/{OWNER}/documents/{document_id}/v{version}/parsed.md",
    )


class FakeCatalog:
    def __init__(self, records, events):
        self.records = records
        self.events = events

    def list_documents(self, owner_id):
        assert owner_id == OWNER
        return self.records

    def reserve_index_version(self, owner_id, document_id, document_name, version):
        self.events.append(("reserve", document_id, version))
        return True

    def finalize_index(self, new_record, owner_id):
        self.events.append(("publish", new_record.document_id, new_record.version))
        return True

    def mark_index_failed(self, owner_id, document_id, version):
        self.events.append(("failed", document_id, version))


class FakeStorage:
    def __init__(self, records, events):
        self.events = events
        self.objects = {item.original_object_key: f"# {item.document_id}".encode() for item in records}

    def get_bytes(self, key):
        return self.objects[key]

    def put_bytes(self, key, data, content_type):
        self.events.append(("store", key))
        self.objects[key] = data


class FakeIngestion:
    async def parse(self, document_id, filename, raw, content_type, pdf_type=None, version=1):
        structured = StructuredDocument(
            document_id=document_id,
            name=filename,
            version=version,
            parser="markdown-structure",
            markdown=f"# rebuilt {document_id}",
            blocks=[DocumentBlock(block_type="heading", text=f"rebuilt {document_id}", heading_level=1)],
        )
        return IngestionResult(
            structured=structured,
            request=IndexRequest(
                document_id=document_id,
                document_name=filename,
                version=version,
                chunks=[ChunkInput(text=f"rebuilt {document_id}", chunk_type="heading")],
            ),
            parser="markdown-structure",
            markdown=structured.markdown,
            low_confidence_pages=[],
        )


class FakeStore:
    def __init__(self, events, fail_document=None):
        self.events = events
        self.fail_document = fail_document

    async def index(self, request):
        self.events.append(("index", request.document_id, request.version))
        if request.document_id == self.fail_document:
            raise RuntimeError("embedding failed")
        return len(request.chunks)

    def delete_document_version(self, owner_id, document_id, version):
        self.events.append(("delete", document_id, version))


def test_rebuild_publishes_new_generation_before_deleting_old_points():
    events = []
    records = [record("resume")]
    result = asyncio.run(IndexRebuilder(
        catalog=FakeCatalog(records, events),
        storage=FakeStorage(records, events),
        store=FakeStore(events),
        ingestion=FakeIngestion(),
    ).rebuild_all(OWNER))

    assert result.succeeded == 1
    assert result.failed == 0
    assert result.results[0].new_version == 2
    assert events.index(("publish", "resume", 2)) < events.index(("delete", "resume", 1))


def test_rebuild_failure_keeps_old_index_and_continues_other_documents():
    events = []
    records = [record("broken"), record("resume")]
    result = asyncio.run(IndexRebuilder(
        catalog=FakeCatalog(records, events),
        storage=FakeStorage(records, events),
        store=FakeStore(events, fail_document="broken"),
        ingestion=FakeIngestion(),
    ).rebuild_all(OWNER))

    assert result.succeeded == 1
    assert result.failed == 1
    assert ("delete", "broken", 1) not in events
    assert ("failed", "broken", 2) in events
    assert ("publish", "resume", 2) in events
