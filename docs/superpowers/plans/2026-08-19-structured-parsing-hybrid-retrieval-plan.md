# Structured PDF Parsing and Hybrid Retrieval Implementation Plan

> **Execution:** Implement sequentially in this worktree with test-driven development. Do not advance from a slice until its focused tests pass.

**Goal:** Preserve PDF and resume structure during ingestion, then retrieve evidence through independent dense and lexical lanes with RRF fusion so entity-specific questions are answerable without admitting unrelated evidence.

**Architecture:** Raw files are normalized into typed document blocks. A deterministic resume enricher groups company, role, project, and responsibility relationships before a structure-aware chunker creates index inputs. Qdrant remains the dense store and scoped chunk source; application-side BM25 supplies the lexical lane for the demo corpus. Retrieval fuses ranked candidates and evidence gating evaluates entity/relation coverage rather than raw cosine alone. Rebuilds publish a new document version before deleting the old version.

**Tech stack:** Python 3.12, FastAPI, PyMuPDF, Qdrant, Pydantic, pytest; Next.js 15, React 19, TypeScript, Vitest.

---

## Task 1: Add normalized document structure models

**Files:**

- Modify: `services/python-rag/app/models.py`
- Create: `services/python-rag/app/document_structure.py`
- Create: `services/python-rag/tests/test_document_structure.py`

**Steps:**

1. Write failing tests for normalized blocks, section ancestry, source positions, PDF bounding boxes, and entity metadata.
2. Add `BoundingBox`, `DocumentBlock`, `StructuredDocument`, and `ChunkEntities` models.
3. Extend `ChunkInput` and `DocumentChunkDetail` with `chunk_type`, `section_path`, `parent_context`, `keywords`, `entities`, `bbox`, and `parser_confidence` while keeping current citation fields intact.
4. Add deterministic helpers that normalize whitespace and serialize section paths.
5. Run:

   `python -m pytest tests/test_document_structure.py -q`

6. Commit: `feat: add normalized document structure models`.

## Task 2: Parse Markdown and plain text structurally

**Files:**

- Create: `services/python-rag/app/markdown_parser.py`
- Modify: `services/python-rag/app/document_processor.py`
- Replace tests: `services/python-rag/tests/test_document_processor.py`
- Create: `services/python-rag/tests/fixtures/structured_resume.md`

**Steps:**

1. Write failing tests proving headings retain ancestry, list items remain atomic, tables remain row-aligned, and blank input is rejected.
2. Implement a deterministic line parser for ATX headings, paragraph groups, list items, fenced code, and Markdown tables.
3. Make `DocumentProcessor.from_text` produce a `StructuredDocument` through the Markdown/plain-text parser.
4. Temporarily retain a compatibility wrapper for callers of `to_index_request`, but remove fixed 900-character splitting from the active ingestion path.
5. Run:

   `python -m pytest tests/test_document_processor.py tests/test_document_structure.py -q`

6. Commit: `feat: parse markdown into structured blocks`.

## Task 3: Parse raw PDF layout and reconstruct reading order

**Files:**

- Modify: `services/python-rag/requirements.txt`
- Create: `services/python-rag/app/layout_parser.py`
- Create: `services/python-rag/tests/test_layout_parser.py`
- Create: `services/python-rag/tests/fixtures/two_column_resume_blocks.json`

**Steps:**

1. Add a pinned PyMuPDF dependency compatible with the service Python image.
2. Write failing tests for full-width headings followed by two columns, repeated header/footer removal, page ordering, font-based heading inference, and list recognition.
3. Implement extraction of spans/blocks from `page.get_text("dict")` including text, font, size, flags, page, and bounding box.
4. Implement a pure reading-order function that can be tested from the JSON fixture without opening a PDF.
5. Detect full-width blocks and columns from page width and horizontal overlap; order by page region, then column and vertical position.
6. Convert ordered layout blocks into the normalized structure model.
7. Add a small in-memory PDF integration test using PyMuPDF to verify coordinates reach the output.
8. Run:

   `python -m pytest tests/test_layout_parser.py -q`

9. Commit: `feat: reconstruct text pdf reading order`.

## Task 4: Enrich resume relationships and create semantic chunks

**Files:**

- Create: `services/python-rag/app/resume_enricher.py`
- Create: `services/python-rag/app/structure_chunker.py`
- Modify: `services/python-rag/app/document_processor.py`
- Create: `services/python-rag/tests/test_resume_enricher.py`
- Create: `services/python-rag/tests/test_structure_chunker.py`

**Steps:**

1. Write a failing regression test for the observed resume facts: 珠海环届云有限公司, 全栈研发, FastGPT, and its responsibility list.
2. Implement section recognition for 工作经历, 项目经历, 教育经历, and skills sections.
3. Implement deterministic company, role, project, date, and responsibility extraction using labels, company suffixes, date patterns, block proximity, and list membership.
4. Mark a complete work-experience group as `resume_experience` and attach typed entities.
5. Write failing chunker tests showing semantic groups stay intact and oversized groups split only between child blocks.
6. Implement a character/token budget chunker that prefixes split children with minimal parent context and repeats entity metadata.
7. Generate normalized lexical keywords for every chunk, preserving English identifiers and Chinese entity phrases.
8. Run:

   `python -m pytest tests/test_resume_enricher.py tests/test_structure_chunker.py tests/test_document_processor.py -q`

9. Commit: `feat: preserve resume relationships in chunks`.

## Task 5: Integrate raw-file parsing into upload

**Files:**

- Create: `services/python-rag/app/ingestion.py`
- Modify: `services/python-rag/app/main.py`
- Modify: `apps/web/app/api/documents/upload/route.ts`
- Modify: `services/python-rag/tests/test_upload.py`
- Create: `services/python-rag/tests/test_ingestion.py`

**Steps:**

1. Write failing tests that text PDFs choose the layout parser, scanned PDFs use MinerU, and Markdown/TXT use structural text parsing.
2. Extract parsing/chunking orchestration into an ingestion service accepting raw bytes, filename, content type, and PDF inspection metadata.
3. Change the Python upload endpoint to parse text PDFs from raw bytes instead of trusting `extracted_markdown`.
4. Keep MinerU as the scanned/image PDF path and structural Markdown fallback.
5. Stop sending extracted Markdown from the Next.js route; continue sending page count and PDF type.
6. Store normalized Markdown output and original bytes in MinIO, then index structured chunks.
7. Return parser and low-confidence page metadata where available.
8. Run:

   `python -m pytest tests/test_ingestion.py tests/test_upload.py -q`

   `pnpm test --run apps/web/app/api/documents/upload/route.test.ts` if a route test is added; otherwise run the full web test suite in Task 9.

9. Commit: `feat: ingest text pdfs from raw layout`.

## Task 6: Store structured chunk payloads and expose details

**Files:**

- Modify: `services/python-rag/app/vector_store.py`
- Modify: `services/python-rag/app/models.py`
- Modify: `services/python-rag/tests/test_document_detail.py`
- Modify: `services/python-rag/tests/test_vector_store.py`
- Modify: `apps/web/components/document-detail-view.tsx`
- Modify: `apps/web/components/document-detail-view.test.tsx`

**Steps:**

1. Write failing tests for indexing and reading every new structural payload field.
2. Store structured metadata on each Qdrant point and deserialize it into document chunk detail responses.
3. Display chunk type, section path, parent context, and recognized entities in the chunk workbench.
4. Keep page navigation and original citations functional.
5. Run:

   `python -m pytest tests/test_vector_store.py tests/test_document_detail.py -q`

   `pnpm test --run components/document-detail-view.test.tsx`

6. Commit: `feat: expose structured chunk metadata`.

## Task 7: Implement lexical BM25 retrieval

**Files:**

- Create: `services/python-rag/app/query_analysis.py`
- Create: `services/python-rag/app/lexical_retriever.py`
- Modify: `services/python-rag/app/vector_store.py`
- Create: `services/python-rag/tests/test_query_analysis.py`
- Create: `services/python-rag/tests/test_lexical_retriever.py`
- Modify: `services/python-rag/tests/test_vector_ownership.py`

**Steps:**

1. Write failing tokenizer tests for Chinese bigram/word signals, company names, relation terms, and case-preserving `FastGPT` identifiers.
2. Implement deterministic query/chunk tokenization without an LLM dependency. Use Latin identifiers, indexed entity phrases, Chinese lexical runs, and character bigrams while removing a small explicit stop-word set.
3. Add a Qdrant scroll method that returns all candidate chunks under the same owner and exact document/version scope as dense retrieval.
4. Write failing BM25 tests where a low-vector-score FastGPT work chunk ranks above unrelated thesis and score-report chunks.
5. Implement BM25, exact phrase bonus, entity match, and requested-relation coverage.
6. Ensure empty or unauthorized document scopes return before Qdrant access.
7. Run:

   `python -m pytest tests/test_query_analysis.py tests/test_lexical_retriever.py tests/test_vector_ownership.py -q`

8. Commit: `feat: add scoped lexical retrieval`.

## Task 8: Fuse dense and lexical results and update evidence gating

**Files:**

- Modify: `services/python-rag/app/models.py`
- Modify: `services/python-rag/app/retrieval.py`
- Modify: `services/python-rag/app/evidence.py`
- Modify: `services/python-rag/app/settings.py`
- Create: `services/python-rag/tests/test_hybrid_retrieval.py`
- Modify: `services/python-rag/tests/test_evidence.py`
- Modify: `services/python-rag/tests/test_graph.py`

**Steps:**

1. Add internal retrieval-signal fields for dense score, lexical score, exact entity match, relation coverage, RRF score, and parser confidence.
2. Write failing tests where lexical retrieval rescues the FastGPT candidate below cosine `0.52` and where an unrelated requirement-review query remains rejected.
3. Run dense and lexical retrieval independently for the base query. Keep optional MQE/HyDE expansion limited to the dense lane.
4. Fuse ranks with RRF and apply a deterministic structural relationship boost.
5. Replace the evidence policy's raw-cosine-only cutoff with fused evidence rules:
   - dense evidence can pass at the existing reliable threshold;
   - exact entity plus requested relation can pass with adequate parser confidence;
   - generic lexical overlap alone cannot pass;
   - candidates missing the requested entity/relation remain rejected.
6. Derive user-facing confidence from evidence quality signals while preserving the existing high/medium/low API.
7. Make hybrid the default retrieval strategy.
8. Run:

   `python -m pytest tests/test_hybrid_retrieval.py tests/test_evidence.py tests/test_graph.py tests/test_query_scope.py -q`

9. Commit: `feat: fuse lexical and vector evidence`.

## Task 9: Add current-user rebuild APIs and UI

**Files:**

- Modify: `services/python-rag/app/document_catalog.py`
- Modify: `services/python-rag/app/vector_store.py`
- Modify: `services/python-rag/app/ingestion.py`
- Modify: `services/python-rag/app/main.py`
- Modify: `services/python-rag/app/models.py`
- Create: `services/python-rag/tests/test_rebuild.py`
- Create: `apps/web/app/api/documents/rebuild/route.ts`
- Modify: `apps/web/components/workspace.tsx`
- Create or modify: `apps/web/components/workspace.test.tsx`

**Steps:**

1. Write failing service tests for new-generation indexing, catalog publication, obsolete-generation cleanup, per-document failure reporting, and owner isolation.
2. Add a rebuild service that reads original MinIO objects, parses and embeds a new version, verifies the indexed count, publishes the catalog version, then deletes old Qdrant points.
3. Add `POST /rag/documents/rebuild` for the authenticated user's documents and return a result per document.
4. Add the matching Next.js authenticated proxy route.
5. Add a `重建全部索引` button, busy state, completion summary, and document-list refresh.
6. Run:

   `python -m pytest tests/test_rebuild.py tests/test_index.py tests/test_document_ownership.py -q`

   `pnpm test --run`

7. Commit: `feat: rebuild structured indexes from source`.

## Task 10: Full regression and acceptance verification

**Files:**

- Modify as needed: `services/python-rag/ARCHITECTURE.md`
- Modify as needed: root README or runbook documentation

**Steps:**

1. Run all Python tests in the service environment:

   `python -m pytest -q`

2. Run all web tests and production build:

   `pnpm test --run`

   `pnpm build`

3. Build the Python service container to verify pinned dependencies:

   `docker compose build python-rag`

4. Start or reuse the local stack, rebuild the demo corpus, and verify these questions end to end:

   - `在FastGPT负责什么岗位` → `全栈研发`, with the work-experience citation.
   - `在珠海环届云有限公司负责什么` → matching responsibilities, no thesis/score-report evidence.
   - `我的毕业论文题目是什么` → `智能旅游规划助手设计与实现`.
   - `新版本的需求评审，需要哪些关键角色参加？` → refused without reliable evidence.

5. Inspect the resume document detail and confirm company-role-project-responsibility metadata appears together.
6. Update architecture documentation with the final data flow and demo scaling limitation of application-side BM25.
7. Run `git diff --check` and review the complete branch diff for unrelated changes.
8. Use the verification-before-completion workflow before claiming success.
9. Commit final documentation/fixes: `docs: describe structured hybrid rag pipeline`.
