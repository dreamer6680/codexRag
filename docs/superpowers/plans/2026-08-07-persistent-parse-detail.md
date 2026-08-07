# Persistent Parse Detail Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist uploaded source files, parsed Markdown, document metadata, and chunk details so the front end can reopen a document detail page with PDF/Markdown comparison and chunk navigation.

**Architecture:** Python RAG stores original and parsed artifacts in MinIO, stores document catalog metadata in Postgres, and stores searchable chunks in Qdrant with chunk offsets. Next.js proxies document list, detail, upload, and original-file endpoints to Python RAG, then renders a workbench-style detail page with a PDF/source pane and Markdown pane.

**Tech Stack:** FastAPI, psycopg, MinIO Python client, Qdrant client, Next.js App Router, React 19, TypeScript.

## Global Constraints

- Keep upload form contract unchanged: `file`, optional `extracted_markdown`, optional `parser`.
- MinIO object keys use `documents/{document_id}/v{version}/original/{filename}` and `documents/{document_id}/v{version}/parsed.md`.
- Qdrant chunk payload must include `chunk_index`, `char_start`, and `char_end`.
- The detail page must support PDF/Markdown side-by-side viewing and chunk navigation.
- Markdown rendering must escape raw document text before formatting and must not inject HTML.
- Exact PDF text highlighting is out of scope for the first version; page-level navigation is sufficient when page metadata exists.

---

## File Structure

- `services/python-rag/app/settings.py`: Add MinIO and Postgres settings.
- `services/python-rag/app/models.py`: Add document metadata, list, detail, and chunk response models; extend `ChunkInput` offsets.
- `services/python-rag/app/document_processor.py`: Populate `char_start` and `char_end`.
- `services/python-rag/app/object_storage.py`: Create focused MinIO artifact storage client.
- `services/python-rag/app/document_catalog.py`: Create focused Postgres document catalog repository.
- `services/python-rag/app/vector_store.py`: Store richer chunk payloads and expose `chunks_for_document`.
- `services/python-rag/app/main.py`: Wire upload persistence and add document list/detail/original endpoints.
- `services/python-rag/requirements.txt`: Add `minio`.
- `services/python-rag/tests/test_document_processor.py`: Cover chunk offsets.
- `services/python-rag/tests/test_document_detail.py`: Cover upload persistence and detail response with fakes.
- `docker-compose.yml`: Add MinIO environment variables to `rag-api`.
- `start_rag.py`: Start MinIO with RAG infrastructure.
- `apps/web/app/api/documents/route.ts`: Proxy document list.
- `apps/web/app/api/documents/[id]/route.ts`: Proxy document detail.
- `apps/web/app/api/documents/[id]/original/route.ts`: Proxy original file stream.
- `apps/web/app/page.tsx`: Replace static detail data with persistent document data and Markdown renderer.
- `apps/web/package.json`: Keep dependencies unchanged for first version.

## Task 1: Chunk Offsets and Qdrant Detail Readback

**Files:**
- Modify: `services/python-rag/app/models.py`
- Modify: `services/python-rag/app/document_processor.py`
- Modify: `services/python-rag/app/vector_store.py`
- Test: `services/python-rag/tests/test_document_processor.py`

**Interfaces:**
- Consumes: `DocumentProcessor.to_index_request(document: Document) -> IndexRequest`
- Produces: `ChunkInput.char_start: int | None`, `ChunkInput.char_end: int | None`
- Produces: `VectorStore.chunks_for_document(document_id: str, version: int | None = None) -> list[DocumentChunkDetail]`

- [ ] **Step 1: Write failing test for chunk offsets**

Add to `services/python-rag/tests/test_document_processor.py`:

```python
def test_processor_records_chunk_offsets():
    processor = DocumentProcessor(chunk_size=10, chunk_overlap=2)
    document = processor.from_text("doc-1", "demo.md", "1234567890abcdefghij")

    request = processor.to_index_request(document)

    assert [(chunk.char_start, chunk.char_end, chunk.text) for chunk in request.chunks] == [
        (0, 10, "1234567890"),
        (8, 18, "90abcdefgh"),
        (16, 20, "ghij"),
    ]
```

- [ ] **Step 2: Run red test**

Run: `cd services/python-rag; .\.venv\Scripts\python.exe -m pytest tests/test_document_processor.py::test_processor_records_chunk_offsets -v`

Expected: FAIL because `ChunkInput` has no `char_start` and `char_end`.

- [ ] **Step 3: Implement offsets**

Update `ChunkInput` in `models.py`:

```python
class ChunkInput(BaseModel):
    text: str = Field(min_length=1)
    page: int | None = None
    section: str | None = None
    confidence: float = Field(default=1, ge=0, le=1)
    char_start: int | None = Field(default=None, ge=0)
    char_end: int | None = Field(default=None, ge=0)
```

Update `DocumentProcessor.to_index_request` chunk creation:

```python
chunks.append(ChunkInput(text=text[start:end], section=f"chars:{start}-{end}", char_start=start, char_end=end))
```

- [ ] **Step 4: Add detail chunk response model and Qdrant readback**

Add to `models.py`:

```python
class DocumentChunkDetail(BaseModel):
    index: int
    page: int | None = None
    section: str | None = None
    text: str
    char_start: int | None = None
    char_end: int | None = None
    confidence: float = Field(default=1, ge=0, le=1)
```

Update `VectorStore.index` payload with:

```python
"chunk_index": i,
"char_start": chunk.char_start,
"char_end": chunk.char_end,
```

Add `VectorStore.chunks_for_document` using Qdrant `scroll` with a `document_id` filter and optional `version` filter, then sort by `chunk_index`:

```python
def chunks_for_document(self, document_id: str, version: int | None = None) -> list[DocumentChunkDetail]:
    must = [FieldCondition(key="document_id", match=MatchValue(value=document_id))]
    if version is not None:
        must.append(FieldCondition(key="version", match=MatchValue(value=version)))
    points, _ = self.client.scroll(
        COLLECTION,
        scroll_filter=Filter(must=must),
        limit=10000,
        with_payload=True,
        with_vectors=False,
    )
    rows = sorted(points, key=lambda point: int(point.payload.get("chunk_index", 0)))
    return [
        DocumentChunkDetail(
            index=int(point.payload.get("chunk_index", index)),
            page=point.payload.get("page"),
            section=point.payload.get("section"),
            text=point.payload["text"],
            char_start=point.payload.get("char_start"),
            char_end=point.payload.get("char_end"),
            confidence=float(point.payload.get("confidence", 1)),
        )
        for index, point in enumerate(rows)
    ]
```

Remember to import `MatchValue` and `DocumentChunkDetail`.

- [ ] **Step 5: Run green test**

Run: `cd services/python-rag; .\.venv\Scripts\python.exe -m pytest tests/test_document_processor.py -v`

Expected: PASS.

## Task 2: MinIO Artifact Storage and Postgres Catalog

**Files:**
- Create: `services/python-rag/app/object_storage.py`
- Create: `services/python-rag/app/document_catalog.py`
- Modify: `services/python-rag/app/settings.py`
- Modify: `services/python-rag/app/models.py`
- Modify: `services/python-rag/requirements.txt`
- Modify: `docker-compose.yml`
- Modify: `start_rag.py`
- Test: `services/python-rag/tests/test_document_detail.py`

**Interfaces:**
- Produces: `ObjectStorage.put_bytes(key: str, data: bytes, content_type: str) -> None`
- Produces: `ObjectStorage.get_bytes(key: str) -> bytes`
- Produces: `ObjectStorage.stream(key: str) -> tuple[bytes, str]`
- Produces: `DocumentCatalog.upsert(record: DocumentRecord) -> None`
- Produces: `DocumentCatalog.list_documents() -> list[DocumentRecord]`
- Produces: `DocumentCatalog.get(document_id: str) -> DocumentRecord | None`

- [ ] **Step 1: Write failing catalog/storage integration test with fakes**

Create `services/python-rag/tests/test_document_detail.py`:

```python
from fastapi.testclient import TestClient

from app.main import app
from app.models import DocumentRecord
from app.vector_store import VectorStore


class FakeStorage:
    def __init__(self):
        self.objects = {}

    def put_bytes(self, key, data, content_type):
        self.objects[key] = (data, content_type)

    def get_bytes(self, key):
        return self.objects[key][0]

    def stream(self, key):
        return self.objects[key]


class FakeCatalog:
    def __init__(self):
        self.records = {}

    def upsert(self, record):
        self.records[record.document_id] = record

    def list_documents(self):
        return list(self.records.values())

    def get(self, document_id):
        return self.records.get(document_id)


def test_upload_persists_artifacts_and_detail(monkeypatch):
    storage = FakeStorage()
    catalog = FakeCatalog()

    async def fake_index(self, request):
        self.last_request = request
        return len(request.chunks)

    def fake_chunks_for_document(self, document_id, version=None):
        return [
            {
                "index": 0,
                "page": None,
                "section": "chars:0-11",
                "text": "# Hello RAG",
                "char_start": 0,
                "char_end": 11,
                "confidence": 1,
            }
        ]

    monkeypatch.setattr("app.main.object_storage", storage)
    monkeypatch.setattr("app.main.document_catalog", catalog)
    monkeypatch.setattr(VectorStore, "index", fake_index)
    monkeypatch.setattr(VectorStore, "chunks_for_document", fake_chunks_for_document)

    client = TestClient(app)
    upload = client.post(
        "/rag/upload",
        files={"file": ("notes.md", b"# Hello RAG", "text/markdown")},
    )

    assert upload.status_code == 200
    document_id = upload.json()["document_id"]
    detail = client.get(f"/rag/documents/{document_id}")

    assert detail.status_code == 200
    payload = detail.json()
    assert payload["document_name"] == "notes.md"
    assert payload["markdown"] == "# Hello RAG"
    assert payload["chunks"][0]["text"] == "# Hello RAG"
    assert storage.objects[f"documents/{document_id}/v1/parsed.md"][0] == b"# Hello RAG"
```

- [ ] **Step 2: Run red test**

Run: `cd services/python-rag; .\.venv\Scripts\python.exe -m pytest tests/test_document_detail.py -v`

Expected: FAIL because the new modules/models/endpoints do not exist.

- [ ] **Step 3: Add settings and dependency**

Add to `requirements.txt`:

```text
minio==7.2.15
```

Add to `Settings`:

```python
postgres_dsn: str = "postgresql://localrag:localrag-change-me@localhost:5432/rag_state"
minio_endpoint: str = "localhost:9000"
minio_access_key: str = "localrag"
minio_secret_key: str = "localrag-change-me"
minio_bucket: str = "rag-documents"
minio_secure: bool = False
```

Add `rag-api` environment variables in `docker-compose.yml`:

```yaml
      MINIO_ENDPOINT: minio:9000
      MINIO_ACCESS_KEY: ${MINIO_ROOT_USER:-localrag}
      MINIO_SECRET_KEY: ${MINIO_ROOT_PASSWORD:-localrag-change-me}
      MINIO_BUCKET: rag-documents
      MINIO_SECURE: "false"
```

Update `start_rag.py` `--with-infra` command to start `qdrant`, `mineru`, `minio`, and `postgres`.

- [ ] **Step 4: Add document response models**

Add to `models.py`:

```python
class DocumentRecord(BaseModel):
    document_id: str
    document_name: str
    version: int
    content_type: str | None = None
    parser: str
    status: Literal["ready", "index_failed"] = "ready"
    page_count: int | None = None
    pdf_type: str | None = None
    chunk_count: int
    original_object_key: str
    markdown_object_key: str
    created_at: str | None = None
    updated_at: str | None = None


class DocumentListResponse(BaseModel):
    documents: list[DocumentRecord]


class DocumentDetailResponse(DocumentRecord):
    original_url: str
    markdown: str
    chunks: list[DocumentChunkDetail]
```

- [ ] **Step 5: Implement `object_storage.py`**

Create an `ObjectStorage` class that creates the bucket when missing, writes bytes with content type, reads bytes, and returns stream bytes plus content type:

```python
from minio import Minio
from .settings import settings


class ObjectStorage:
    def __init__(self) -> None:
        self.bucket = settings.minio_bucket
        self.client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )

    def ensure_bucket(self) -> None:
        if not self.client.bucket_exists(self.bucket):
            self.client.make_bucket(self.bucket)

    def put_bytes(self, key: str, data: bytes, content_type: str) -> None:
        from io import BytesIO
        self.ensure_bucket()
        self.client.put_object(self.bucket, key, BytesIO(data), len(data), content_type=content_type)

    def get_bytes(self, key: str) -> bytes:
        response = self.client.get_object(self.bucket, key)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()

    def stream(self, key: str) -> tuple[bytes, str]:
        response = self.client.get_object(self.bucket, key)
        try:
            content_type = response.headers.get("content-type", "application/octet-stream")
            return response.read(), content_type
        finally:
            response.close()
            response.release_conn()
```

- [ ] **Step 6: Implement `document_catalog.py`**

Create `DocumentCatalog` with `_connect`, `ensure_schema`, `upsert`, `list_documents`, and `get`. `ensure_schema` creates `rag_documents` if it does not exist. `upsert` uses `ON CONFLICT (document_id) DO UPDATE`. Return rows as `DocumentRecord`.

- [ ] **Step 7: Run green test**

Run: `cd services/python-rag; .\.venv\Scripts\python.exe -m pytest tests/test_document_detail.py -v`

Expected: PASS.

## Task 3: Upload Persistence and Detail Endpoints

**Files:**
- Modify: `services/python-rag/app/main.py`
- Modify: `services/python-rag/tests/test_upload.py`
- Test: `services/python-rag/tests/test_document_detail.py`

**Interfaces:**
- Consumes: `object_storage`, `document_catalog`, `VectorStore.chunks_for_document`
- Produces: `GET /rag/documents`
- Produces: `GET /rag/documents/{document_id}`
- Produces: `GET /rag/documents/{document_id}/original`

- [ ] **Step 1: Extend upload tests with fake storage/catalog**

In existing upload tests, monkeypatch `app.main.object_storage` and `app.main.document_catalog` with fakes so upload tests do not require MinIO or Postgres.

- [ ] **Step 2: Implement module-level clients**

In `main.py`, import and create:

```python
from fastapi.responses import Response
from .document_catalog import DocumentCatalog
from .object_storage import ObjectStorage

object_storage = ObjectStorage()
document_catalog = DocumentCatalog()
```

Use the non-relative import variant in the `__package__ in (None, "")` branch.

- [ ] **Step 3: Persist artifacts during upload**

After parsing `content` and before indexing, compute:

```python
version = 1
original_key = f"documents/{document_id}/v{version}/original/{filename}"
markdown_key = f"documents/{document_id}/v{version}/parsed.md"
object_storage.put_bytes(original_key, raw, file.content_type or "application/octet-stream")
object_storage.put_bytes(markdown_key, content.encode("utf-8"), "text/markdown; charset=utf-8")
```

After successful indexing, write `DocumentRecord` to catalog with `chunk_count=count`, `parser=parser_used`, and PDF metadata when available from optional form data in later front-end proxy payloads. For this first pass, keep `page_count=None` and `pdf_type=None` unless form fields are added.

- [ ] **Step 4: Add list endpoint**

```python
@app.get("/rag/documents", response_model=DocumentListResponse)
async def documents():
    return DocumentListResponse(documents=document_catalog.list_documents())
```

- [ ] **Step 5: Add detail endpoint**

```python
@app.get("/rag/documents/{document_id}", response_model=DocumentDetailResponse)
async def document_detail(document_id: str):
    record = document_catalog.get(document_id)
    if not record:
        raise HTTPException(404, "Document not found")
    markdown = object_storage.get_bytes(record.markdown_object_key).decode("utf-8")
    chunks = VectorStore().chunks_for_document(document_id, record.version)
    return DocumentDetailResponse(**record.model_dump(), original_url=f"/rag/documents/{document_id}/original", markdown=markdown, chunks=chunks)
```

- [ ] **Step 6: Add original endpoint**

```python
@app.get("/rag/documents/{document_id}/original")
async def document_original(document_id: str):
    record = document_catalog.get(document_id)
    if not record:
        raise HTTPException(404, "Document not found")
    data, content_type = object_storage.stream(record.original_object_key)
    return Response(content=data, media_type=content_type)
```

- [ ] **Step 7: Run endpoint tests**

Run: `cd services/python-rag; .\.venv\Scripts\python.exe -m pytest tests/test_upload.py tests/test_document_detail.py -v`

Expected: PASS.

## Task 4: Frontend Proxies and Persistent Document State

**Files:**
- Create: `apps/web/app/api/documents/route.ts`
- Create: `apps/web/app/api/documents/[id]/route.ts`
- Create: `apps/web/app/api/documents/[id]/original/route.ts`
- Modify: `apps/web/app/page.tsx`

**Interfaces:**
- Consumes: Python `GET /rag/documents`, `GET /rag/documents/{id}`, and original stream endpoint.
- Produces: `DocumentRow.document_id`
- Produces: `DocumentDetailData` in front-end state.

- [ ] **Step 1: Add document list proxy**

Create `apps/web/app/api/documents/route.ts`:

```typescript
import { NextResponse } from "next/server";

export const runtime = "nodejs";

export async function GET() {
  const upstream = process.env.RAG_API_URL ?? "http://localhost:8001";
  try {
    const response = await fetch(`${upstream}/rag/documents`, { cache: "no-store" });
    const payload = await response.json();
    return NextResponse.json(payload, { status: response.status });
  } catch {
    return NextResponse.json({ detail: "无法连接本地 RAG 文档服务" }, { status: 503 });
  }
}
```

- [ ] **Step 2: Add detail proxy**

Create `apps/web/app/api/documents/[id]/route.ts` with `GET(_request, { params })` that fetches `${upstream}/rag/documents/${params.id}` and returns JSON.

- [ ] **Step 3: Add original stream proxy**

Create `apps/web/app/api/documents/[id]/original/route.ts` with `GET(_request, { params })` that fetches `${upstream}/rag/documents/${params.id}/original`, copies `content-type`, and returns a `Response` with the upstream array buffer.

- [ ] **Step 4: Add front-end data types**

In `page.tsx`, add:

```typescript
type DocumentChunk = { index: number; page?: number | null; section?: string | null; text: string; char_start?: number | null; char_end?: number | null; confidence: number };
type DocumentDetailData = DocumentRow & { content_type?: string | null; parser: string; page_count?: number | null; pdf_type?: string | null; original_url: string; markdown: string; chunks: DocumentChunk[] };
```

Extend `DocumentRow` with `document_id`, `content_type?`, `parser?`, `page_count?`, and `pdf_type?`.

- [ ] **Step 5: Load persistent document list**

On mount, fetch `/api/documents`, map returned records to table rows, and merge them ahead of demo rows. Upload success should insert the returned document id and then call `loadDocuments()`.

- [ ] **Step 6: Load detail on click**

Change document table `onDetail` to accept `document_id`. If the row has a real id, fetch `/api/documents/${document_id}`, set `selectedDocument`, reset `activeChunk`, and switch to `detail`.

- [ ] **Step 7: Build safe Markdown renderer**

Add local helpers in `page.tsx`:

```typescript
function escapeHtml(value: string) {
  return value.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function renderMarkdown(markdown: string) {
  // Convert escaped lines to React elements for headings, lists, blockquotes,
  // fenced code blocks, rules, simple tables, and paragraphs.
}
```

The renderer must return React nodes, not use `dangerouslySetInnerHTML`.

## Task 5: Detail Workbench UI

**Files:**
- Modify: `apps/web/app/page.tsx`

**Interfaces:**
- Consumes: `DocumentDetailData`
- Produces: PDF/source pane, chunk rail, Markdown render/raw/chunk tabs.

- [ ] **Step 1: Replace static `Detail` component props**

Change signature to:

```typescript
function Detail({
  document,
  activeChunk,
  setActiveChunk,
  back,
}: {
  document: DocumentDetailData | null;
  activeChunk: number;
  setActiveChunk: (value: number) => void;
  back: () => void;
})
```

- [ ] **Step 2: Add empty/loading fallback**

If `document` is null, render a card that says no document is selected and a back button.

- [ ] **Step 3: Add header metrics**

Render title, parser, status, page count, chunk count, PDF type, and OCR/page availability. Keep layout responsive.

- [ ] **Step 4: Add chunk rail**

Render horizontal chunk buttons from `document.chunks`. The active button gets a blue top line and includes index, page if present, and character span.

- [ ] **Step 5: Add original pane**

If `document.content_type` includes `pdf`, render:

```tsx
<iframe src={`${document.original_url}${activeChunkPage ? `#page=${activeChunkPage}` : ""}`} />
```

Otherwise render escaped source text from `document.markdown`.

- [ ] **Step 6: Add Markdown pane**

Render segmented buttons for `渲染视图`, `原始 Markdown`, and `当前 chunk`. The render tab uses `renderMarkdown(document.markdown)`, raw tab uses `<pre>`, and chunk tab uses the active chunk text.

- [ ] **Step 7: Run frontend build**

Run: `cd apps/web; npm run build`

Expected: PASS.

## Task 6: End-to-End Verification

**Files:**
- No code files unless verification exposes defects.

**Interfaces:**
- Verifies: upload, list, detail, original stream, front-end build.

- [ ] **Step 1: Install Python dependencies if needed**

Run: `cd services/python-rag; .\.venv\Scripts\python.exe -m pip install -r requirements.txt`

Expected: `minio` is installed.

- [ ] **Step 2: Run backend tests**

Run: `cd services/python-rag; .\.venv\Scripts\python.exe -m pytest -v`

Expected: PASS.

- [ ] **Step 3: Run frontend build**

Run: `cd apps/web; npm run build`

Expected: PASS.

- [ ] **Step 4: Start infrastructure**

Run: `docker compose up -d qdrant mineru minio postgres`

Expected: all four services show running in `docker compose ps`.

- [ ] **Step 5: Smoke test health**

Run:

```powershell
curl.exe http://127.0.0.1:8001/health
curl.exe http://127.0.0.1:6333/collections
curl.exe http://127.0.0.1:9000/minio/health/live
```

Expected: RAG health JSON, Qdrant ok response, and MinIO live response.

## Self-Review Notes

- Spec coverage: storage responsibilities, list/detail/original APIs, chunk metadata, Markdown rendering, PDF/Markdown comparison, and first-version limitations are covered.
- Placeholder scan: no `TBD`, `TODO`, or unspecified implementation steps remain.
- Type consistency: `DocumentRecord`, `DocumentDetailResponse`, `DocumentChunkDetail`, and front-end `DocumentDetailData` are named consistently across tasks.
