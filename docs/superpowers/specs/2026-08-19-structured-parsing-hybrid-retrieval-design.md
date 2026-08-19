# Structured PDF Parsing and Hybrid Retrieval Design

Date: 2026-08-19

## Goal

Improve answer quality by fixing document parsing and chunk structure before changing retrieval. The system must preserve relationships such as company, role, project, and responsibilities, then combine lexical and dense-vector retrieval so exact entities can rescue relevant evidence with a weak cosine score.

This is a demo-stage design. Existing chunk payloads do not require backward compatibility. The current user's indexes may be rebuilt from original objects stored in MinIO, and obsolete index generations may be deleted immediately after a successful switch.

## Current Failure

The current upload path accepts Markdown produced by `pdf-inspector`, and `DocumentProcessor` splits the resulting text into 900-character windows with 120-character overlap. In multi-column PDFs, text is already interleaved before chunking. Fixed character windows then separate or mix related facts.

For the resume regression case, the source PDF visually relates:

- company: 珠海环届云有限公司
- role: 全栈研发
- project: FastGPT
- responsibilities: documentation migration, link service, scheduled knowledge-base synchronization, and customer customization

The indexed text loses those relationships. Dense retrieval scores for the FastGPT and company questions remain below the evidence threshold, while exact lexical matches cannot enter the candidate set because the current lexical overlap is only a post-retrieval sorting bonus.

## Chosen Approach

Use raw PDF layout extraction followed by a common structured document model and structure-aware chunker. Add a resume-specific relationship enrichment step on top of the common model. Retrieval uses two independent lanes: dense vectors and lexical BM25/exact-entity matching. The application fuses their ranks with reciprocal rank fusion (RRF) and applies evidence gating after fusion.

The design avoids an LLM dependency in parsing. Local models may be unavailable, and parsing must be deterministic, testable, and repeatable.

## Parsing Pipeline

### PDF documents

For text PDFs, the Python service parses the original PDF bytes and extracts text spans with page number, bounding box, font size, font style, and block identity. It then:

1. removes blank and repeated decorative spans;
2. groups spans into visual lines and blocks;
3. detects full-width headers and page regions;
4. detects columns from horizontal block positions;
5. orders blocks by page, region, column, and vertical position;
6. infers headings, paragraphs, list items, and table-like rows;
7. emits a normalized document structure.

`pdf-inspector` remains responsible for lightweight PDF classification, page count, and OCR hints in the web upload route. Its Markdown is no longer the primary source for text PDFs.

For scanned or image-heavy PDFs, the service uses MinerU/OCR output and passes the resulting Markdown through the same normalized structure stage. If layout extraction fails, the system falls back to structure-aware Markdown parsing, not fixed character windows.

### Markdown and text documents

Markdown parsing preserves heading hierarchy, lists, code fences, and tables. Plain text is split by paragraphs and recognizable heading/list patterns. Both sources emit the same normalized block model as PDFs.

## Normalized Structure

Each block contains:

- `block_type`: heading, paragraph, list item, table row, or other;
- `text`;
- `page` and optional PDF `bbox`;
- `section_path` containing its heading ancestry;
- source offsets when available;
- parser confidence;
- structural attributes such as heading level and list nesting.

The normalized structure is deterministic and contains enough source location data for citations and debugging.

## Resume Relationship Enrichment

The general structure pipeline detects resume sections using headings such as 工作经历, 项目经历, 教育经历, and 技能. Inside work/project sections, a deterministic enricher recognizes:

- company or organization;
- role or position;
- project or platform;
- date range;
- responsibilities and achievements.

It uses section context, line proximity, visual alignment, common labels, date patterns, and list membership. The result is an enriched semantic unit. Uncertain fields remain absent rather than being invented.

This enrichment is additive. Non-resume documents continue through the common structure pipeline without resume assumptions.

## Structure-Aware Chunking

Chunks are formed from semantic units rather than character windows.

- Headings stay with their following content.
- Lists and table rows are not split in the middle when they fit within the token budget.
- A resume work-experience unit keeps company, role, project, and responsibilities together.
- Oversized units are split only at child-block boundaries.
- Every child chunk repeats the minimal parent context needed to preserve meaning.
- A small token overlap is permitted only between oversized sibling chunks.

Each indexed chunk stores:

- `chunk_type`;
- `section_path`;
- `parent_context`;
- `keywords`;
- `entities`;
- `page` and optional `bbox`;
- source offsets;
- parser confidence;
- original chunk text used for citation.

## Hybrid Retrieval

### Query normalization

The query is normalized without losing the original text. The retriever extracts:

- Chinese word tokens;
- English identifiers while preserving original forms such as `FastGPT`;
- normalized lowercase variants;
- entity-like phrases, company suffixes, quoted terms, and role/project terms;
- relation intent such as 岗位, 职责, 题目, 时间, or 公司.

### Dense lane

The dense lane queries Qdrant with the existing owner, active-version, and selected-document filters. It returns more candidates than the final answer needs so fusion has sufficient coverage.

### Lexical lane

For the demo-sized corpus, the lexical retriever reads chunks in the same owner/version/document scope and computes BM25 in the application. It combines token BM25 with exact phrase and indexed-entity matches. This adds no new infrastructure and keeps Chinese tokenization under application control.

The lexical retriever is behind an interface so it can later be replaced with Qdrant sparse vectors or Elasticsearch without changing fusion and evidence gating.

### Fusion and structural reranking

The two ranked lists are combined using RRF. Scores from dense and lexical retrieval are not compared directly.

After fusion, a structural reranker boosts candidates that satisfy the requested relationship, for example:

- query entity `FastGPT` matches the chunk project entity;
- requested relation 岗位 is present in the same enriched work unit;
- company name and responsibilities occur in the same unit.

An exact entity match may admit a candidate whose dense cosine score is below the old `0.52` evidence threshold. It does not automatically make the answer reliable: relationship coverage and parser confidence must still pass evidence gating.

## Evidence Gating

Evidence gating runs after fusion and considers:

- exact entity/phrase coverage;
- requested relation coverage;
- dense and lexical rank agreement;
- structural-unit integrity;
- parser confidence;
- contradiction or ambiguity between candidates.

Unrelated questions still fail closed. A weak semantic match to a thesis, score report, or unrelated test case is insufficient when the requested entities or relationships are absent.

Confidence labels are derived from the fused evidence signals rather than raw cosine similarity alone.

## Upload and Rebuild Behavior

New uploads always use the new parser and chunker.

A user-scoped rebuild operation reads each document's original object from MinIO, reparses it, embeds the new chunks, and replaces that document's indexed points. The demo does not preserve old chunk schema or serve mixed schemas.

Because Qdrant does not provide a transaction spanning all points in a document, replacement uses an index generation (the existing document version can serve this role) and an atomic catalog switch:

1. parse, chunk, and embed the complete replacement before changing active state;
2. write all points under a new generation and verify their count;
3. switch the catalog's active generation and update chunk count/parser metadata;
4. delete the obsolete generation after the catalog switch.

If any step before the catalog switch fails, the old generation remains active. Demo mode does not require serving old and new chunk schemas at the same time because only the catalog-selected generation is searchable.

A failure in one document is reported and does not prevent other documents from rebuilding. The UI provides rebuild-all and per-document retry actions for the current user.

## API and UI Changes

- Upload responses include parser name, structured chunk count, and low-confidence pages.
- Document detail exposes chunk type, section path, entities, parent context, and source location.
- A user-scoped rebuild endpoint returns per-document success/failure results.
- The document UI includes a rebuild-all action and displays individual failures.
- The existing owner and selected-document authorization rules remain mandatory on every retrieval and rebuild path.

## Testing Strategy

Development follows test-first slices.

### Parser and chunker regression tests

- A two-column resume fixture reconstructs the intended reading order.
- Company, role, project, and responsibilities form one work-experience unit.
- Oversized responsibility lists split only on item boundaries and retain parent context.
- Markdown headings, lists, and tables are not cut through the middle.
- Parser fallback is deterministic and never returns blank chunks.

### Retrieval tests

- A low dense-score `FastGPT` candidate is retrieved through the lexical lane.
- The query `在FastGPT负责什么岗位` ranks the enriched work unit first.
- The query `在珠海环届云有限公司负责什么` returns the matching responsibilities.
- The thesis-title query remains answerable.
- An unsupported product-requirement-review question is rejected.
- Owner, active-version, and selected-document filters apply identically to both lanes.

### Rebuild tests

- Successful rebuild replaces obsolete points and updates the catalog.
- Parsing or embedding failure leaves the previously usable document index intact.
- A failure in one document does not stop the remaining rebuild batch.

## Acceptance Criteria

1. `在FastGPT负责什么岗位` answers `全栈研发` and cites the corresponding work-experience chunk.
2. `在珠海环届云有限公司负责什么` returns that company's responsibilities without thesis or score-report noise.
3. Document detail visibly preserves company-role-project-responsibility relationships.
4. Unsupported questions do not produce answers from weak vector similarity.
5. Rebuilding the demo corpus makes every successful document use the new structure.
6. Automated tests cover layout ordering, structured chunking, both retrieval lanes, fusion, refusal, authorization scope, and rebuild atomicity.

## Deferred Work

- production-scale distributed lexical indexing;
- general-purpose LLM-based document restructuring;
- backward compatibility with old chunk payloads;
- cross-encoder reranking, which can be added later if a reliable local reranker is available;
- advanced table reconstruction and image-caption understanding beyond the demo's core resume and thesis cases.
