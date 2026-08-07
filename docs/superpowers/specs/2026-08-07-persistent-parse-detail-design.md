# Persistent Parse Detail Design

## Goal

Build a persistent parse detail workflow for uploaded documents so users can reopen a document after refresh and inspect the original file, parsed Markdown, and retrieval chunks side by side.

## Scope

This feature covers the local Python RAG service, MinIO object storage, Qdrant chunk retrieval, and the Next.js document detail UI. The first implementation targets PDF, TXT, and Markdown uploads already accepted by `/rag/upload`.

## Storage Responsibilities

- MinIO stores durable document artifacts:
  - `documents/{document_id}/v{version}/original/{filename}` for the uploaded source file.
  - `documents/{document_id}/v{version}/parsed.md` for the parsed Markdown or normalized text.
- Postgres stores the document catalog:
  - `document_id`, `document_name`, `version`, `content_type`, `parser`, `status`, `page_count`, `pdf_type`, `chunk_count`, `original_object_key`, `markdown_object_key`, and timestamps.
- Qdrant stores retrieval chunks and metadata:
  - `document_id`, `document_name`, `version`, `chunk_index`, `page`, `section`, `text`, `confidence`, `char_start`, and `char_end`.

MinIO is the source of truth for original and parsed artifacts. Qdrant is the source of truth for searchable chunks. Postgres is the source of truth for document listings and object keys.

## API Design

### Upload

`POST /rag/upload` keeps the existing multipart form contract:

- Required form field: `file`
- Optional form fields: `extracted_markdown`, `parser`

On success it persists artifacts, indexes chunks, records metadata, and returns:

```json
{
  "document_id": "uuid",
  "document_name": "report.pdf",
  "version": 1,
  "indexed_chunks": 12,
  "parser": "mineru",
  "status": "ready"
}
```

### Document List

`GET /rag/documents` returns document rows for the front-end document table:

```json
{
  "documents": [
    {
      "document_id": "uuid",
      "document_name": "report.pdf",
      "version": 1,
      "content_type": "application/pdf",
      "parser": "mineru",
      "status": "ready",
      "page_count": 8,
      "pdf_type": "Scanned",
      "chunk_count": 12,
      "created_at": "2026-08-07T00:00:00Z",
      "updated_at": "2026-08-07T00:00:00Z"
    }
  ]
}
```

### Document Detail

`GET /rag/documents/{document_id}` returns all data needed for the parse detail page:

```json
{
  "document_id": "uuid",
  "document_name": "report.pdf",
  "version": 1,
  "content_type": "application/pdf",
  "parser": "mineru",
  "status": "ready",
  "page_count": 8,
  "pdf_type": "Scanned",
  "chunk_count": 12,
  "original_url": "/api/documents/uuid/original",
  "markdown": "# Parsed content",
  "chunks": [
    {
      "index": 0,
      "page": 1,
      "section": "chars:0-900",
      "text": "Parsed chunk",
      "char_start": 0,
      "char_end": 900,
      "confidence": 1
    }
  ],
  "created_at": "2026-08-07T00:00:00Z",
  "updated_at": "2026-08-07T00:00:00Z"
}
```

### Original File

`GET /rag/documents/{document_id}/original` streams the original file from MinIO with the stored content type. Next.js proxies this endpoint so the browser never needs MinIO credentials.

## Frontend Design

The document detail page is a parse inspection workbench:

```text
[document title, parser, status, page count, chunk count, OCR state]

[chunk rail: 01 02 03 04 ...]

[left: original PDF or source preview]  [right: Markdown render / raw Markdown / chunk text]
```

The signature element is the chunk rail: a compact top strip of numbered chunk cells that acts like a document ruler. Selecting a chunk updates the right pane and, when page data exists, points the PDF pane to the relevant page.

Color and type stay close to the current workspace UI:

- `paper`: `#ffffff`
- `ink`: `#18181b`
- `blueprint`: `#2563eb`
- `amber-note`: `#f59e0b`
- `quiet-line`: `#e4e4e7`

The UI remains restrained and work-focused. The visual risk is the document-ruler chunk rail, which makes parsing structure visible without turning the screen into a dashboard poster.

## Markdown Rendering

The first version uses a small client-side Markdown renderer without adding a dependency. It supports headings, paragraphs, unordered and ordered lists, blockquotes, fenced code blocks, horizontal rules, inline code, bold text, and simple pipe tables. Rendered output is escaped before formatting so parsed documents cannot inject HTML.

## Error Handling

- If MinIO is unavailable during upload, the upload fails before indexing and returns a 503.
- If indexing fails after artifacts are stored, metadata is recorded as `index_failed` when possible and the upload returns the existing failure response.
- If a document id is unknown, detail endpoints return 404.
- If the original file cannot be streamed, the original endpoint returns 503 with a direct storage error.

## First-Version Limitations

- Exact PDF text highlighting is out of scope. The PDF viewer can jump by page only when chunk page metadata exists.
- Existing documents indexed before this feature may not have Postgres rows or object artifacts. They will not appear in the persistent document list until re-uploaded.
- For TXT and Markdown uploads, the left pane shows the original text instead of a PDF preview.
