# Enterprise RAG Core Accuracy Design

Date: 2026-08-20

## Goal

Redesign the local knowledge-base retrieval core so answerable questions are not missed, unrelated documents are not cited, and every answer remains strictly grounded in the user's active documents. The system must fix both observed failures:

1. `FastGPT是什么` must retrieve and accept the resume evidence that says `FastGPT，AI Agent 平台`.
2. FastGPT questions must not cite the unrelated thesis.

The system cannot mathematically guarantee zero error for every possible natural-language question. Enterprise readiness is therefore defined by explicit invariants, a versioned evaluation corpus, measurable service-level objectives, and merge-blocking regression gates. Critical known facts and authorization boundaries have 100% requirements.

## Product Mode

The chosen mode is **strict knowledge grounding**.

- The assistant may state only facts supported by active user documents.
- A short supported answer is preferred over an expanded answer using model knowledge.
- For the current source, `FastGPT 是一个 AI Agent 平台。[1]` is valid.
- Features not stated in the evidence must not be added from model memory.
- When no candidate satisfies the query-evidence contract, the system refuses.

## Evidence from the Current System

The failure was reproduced against the live PostgreSQL catalog and Qdrant index.

For `FastGPT是什么`:

- the resume chunk is lexical rank 1;
- BM25/exact score is `4.462`;
- `exact_entity_match` is true;
- dense score is `0.443`;
- `relation_coverage` is false;
- the evidence policy rejects the chunk because `0.443 < 0.52` and a definition relation does not exist.

The same fused candidate set contains unrelated thesis chunks with dense scores around `0.38-0.44`. They have no FastGPT entity or relation coverage. This proves that dense similarity alone introduces cross-document noise.

The live five-query baseline also showed:

- FastGPT definition: correct evidence recalled but rejected;
- FastGPT position: correct evidence accepted;
- company responsibilities: correct evidence accepted with duplicate same-page evidence;
- thesis title: six scattered thesis pages accepted rather than a title fact;
- unsupported product-review-role question: six thesis chunks accepted, a false-positive failure.

## Parsing Root Cause

The original thesis PDF was rendered and its text layer extracted. Page 1 clearly contains:

```text
题目  智能旅游规划助手设计与实现
学生姓名  孟哲
指导教师  韩婷婷
```

The active Qdrant generation contains no exact title phrase and no `题目` field. The loss occurs after layout extraction:

- the layout parser classifies large or bold cover rows as headings;
- `StructureAwareChunker.chunk` unconditionally skips every heading block;
- front-matter rows and heading-only facts disappear from the index;
- the remaining evidence gate attempts to infer title relevance from arbitrary body chunks.

This is an indexing fidelity defect, not a retrieval-threshold problem.

## Chosen Architecture

Use a deterministic **query-evidence contract** on top of faithful structured indexing and independent dense/lexical recall. Candidate generation remains broad; evidence eligibility becomes strict and explainable.

```text
Raw source
  -> layout-preserving parse
  -> semantic units and document facts
  -> structure-aware chunks with lineage
  -> dense + lexical indexes

Question
  -> query contract
  -> dense lane + lexical/entity lane
  -> rank fusion
  -> contract eligibility
  -> relation-aware reranking
  -> semantic deduplication
  -> evidence gate
  -> extractive fact answer or grounded LLM answer
```

The core path is deterministic and does not depend on an available chat or reranking model. A cross-encoder may later rerank already eligible candidates but may never override hard grounding rules.

## Structured Indexing Fidelity

### Preserve every meaningful block

Headings are indexed rather than discarded. A heading is attached to the following body block when possible. A standalone heading with factual value remains a searchable chunk.

Decorative repeated headers, footers, and page numbers may be removed only through explicit repeated-marginal rules. Font size alone is insufficient reason to discard text.

### Semantic unit assembly

Adjacent layout blocks are assembled before chunk creation.

- Heading plus following paragraphs form a section unit.
- Cover labels and values on the same visual row form key-value facts.
- Values split across adjacent lines are joined when alignment and punctuation indicate continuity.
- List headings remain with their list items.
- Resume company, role, project, dates, and responsibilities remain one experience unit.
- Tables retain row and header context.

Each semantic unit receives a stable `semantic_unit_id` derived from document ID, version, page, and source block positions.

### Document metadata facts

Front matter emits a `document_metadata` chunk and structured fact fields when present:

- `title`;
- `author` or student name;
- `organization` or school;
- `department`;
- `major`;
- `advisor`;
- `completion_date`;
- `document_type`.

The source text and page/bounding boxes remain attached for human-verifiable citations. Uncertain fields are omitted rather than guessed.

### Page coverage invariant

For every page with extractable non-decorative text:

- at least one indexed semantic unit must reference the page; or
- the parser must emit an explicit exclusion reason such as repeated footer.

Index publication fails when meaningful source text disappears without an exclusion record. Coverage statistics are stored in parser metadata and exposed to rebuild diagnostics.

### Chunk payload

Every indexed chunk carries:

- document ID, version, name, and owner;
- page and bounding box;
- `semantic_unit_id`;
- chunk type and section path;
- original evidence text;
- keywords and structured entities;
- structured fact fields;
- document type;
- parser confidence;
- source block count and coverage lineage.

Demo mode permits a destructive full rebuild of current indexes after this schema changes. Mixed old/new payload generations are not served.

## Query Contract

`analyze_query` produces a `QueryContract` rather than only tokens and a small relation set.

```python
QueryContract(
    original_question: str,
    tokens: list[str],
    entities: list[QueryEntity],
    relation: RelationType,
    answer_type: AnswerType,
    required_concepts: list[str],
    target_document_type: str | None,
    named_entity_required: bool,
)
```

### Supported relations

- `definition`: 是什么、介绍、含义、指什么;
- `position`: 岗位、职位、职务;
- `responsibilities`: 负责什么、职责、做了什么;
- `title`: 题目、标题、名称;
- `time`: 时间、何时、哪一年;
- `attributes`: 特点、技术栈、功能、作用;
- `list`: 有哪些、包括什么;
- `identity`: 作者、学生、导师、公司;
- `general`: no reliable relation classification.

Relations use deterministic Chinese/English patterns and are extensible through a registry. Pattern tests cover positive and negative phrases.

### Entity and alias handling

Latin product names retain case-preserving display forms and lowercase matching forms. Exact phrases, quoted phrases, company names, indexed entity aliases, and normalized punctuation variants are recognized.

Aliases may come only from indexed facts or an explicit application dictionary. The query analyzer does not invent aliases with an LLM.

## Candidate Generation

Dense and lexical lanes operate independently in the identical owner/version/document scope.

### Dense lane

The dense lane retrieves a broad top-K without treating cosine similarity as evidence validity. Dense score is one ranking signal only.

### Lexical and fact lane

BM25 scoring is combined with:

- exact named-entity matches;
- exact structured fact values;
- aliases;
- relation-specific fields;
- phrase and token coverage;
- section and document-type matches.

Document metadata facts and resume experience facts are searchable in the same lane as normal chunks.

### Fusion

Reciprocal rank fusion combines dense and lexical/fact ranks. Raw BM25 and cosine scores are never compared directly. Fusion produces candidates, not accepted evidence.

## Candidate Feature Model

Each fused candidate receives an explainable `EvidenceSignals` value:

```python
EvidenceSignals(
    entity_coverage: float,
    required_concept_coverage: float,
    relation_coverage: bool,
    structured_fact_match: bool,
    exact_phrase_match: bool,
    dense_score: float | None,
    lexical_score: float | None,
    parser_confidence: float,
    document_type_match: bool,
    semantic_unit_integrity: bool,
)
```

These values travel with retrieval traces and tests. Confidence is derived from evidence support, not copied from dense similarity.

## Contract Eligibility Rules

Eligibility is evaluated before final evidence selection.

### Named-entity questions

When `named_entity_required` is true, evidence must cover the named entity or an explicit alias. Dense similarity alone can never satisfy this rule.

For `FastGPT是什么`, a thesis chunk without FastGPT has zero eligibility regardless of cosine score.

### Definition questions

Evidence must contain:

1. the target entity; and
2. a definition/apposition pattern, structured type fact, or an intact semantic unit that directly identifies the entity.

`FastGPT，AI Agent 平台` satisfies the contract.

### Structured fact questions

Title, author, advisor, major, time, and position queries prefer matching structured fields. A generic body paragraph containing the word `题目` or a high dense score does not satisfy a title query.

For `我的毕业论文题目是什么`, eligible evidence must come from a thesis-like document and contain a `title` fact or an explicit title statement.

### Responsibility and attribute questions

Evidence must contain the target entity when one is named and an intact unit that expresses the requested relation. A resume experience unit can satisfy responsibilities through its structured role and responsibility children.

### General questions without named entities

Because no hard entity exists, a candidate must satisfy both:

- meaningful required-concept or phrase coverage; and
- relation coverage, structured fact match, or agreement between independent retrieval lanes.

Dense score alone is insufficient. This prevents the unsupported product-review-role query from using generic thesis text.

### Parser quality

Candidates below the parser-confidence floor or without source lineage are ineligible. No ranking signal can override missing source evidence.

## Relation-Aware Reranking

Eligible candidates are reranked using deterministic support features:

1. structured fact match;
2. exact entity plus relation coverage;
3. exact phrase coverage;
4. agreement between lexical and dense lanes;
5. semantic-unit integrity;
6. parser confidence;
7. fused rank.

An optional local cross-encoder may reorder candidates inside the eligible set. If unavailable, deterministic ranking remains complete. The cross-encoder cannot make an ineligible candidate citable.

## Deduplication and Evidence Diversity

Evidence is deduplicated by `semantic_unit_id` first, then by normalized text hash. Multiple chunks from one oversized unit may contribute to context, but the UI presents a single source group unless separate pages materially support separate claims.

Default final selection rules:

- one best semantic unit per fact;
- no duplicate same-page excerpts;
- no unrelated document added merely for document diversity;
- additional evidence only when it adds a distinct supported claim.

For the FastGPT position question, the result should cite the resume unit once, not append an unrelated thesis page.

## Evidence Gate and Confidence

The fixed `dense >= 0.52` rule is removed as the primary gate.

The new gate receives `QueryContract` plus candidate signals. It first applies hard eligibility, then assigns confidence from support strength:

- **high**: structured fact match, or exact entity/relation evidence with intact source lineage;
- **medium**: strong concept and relation coverage confirmed by two retrieval lanes;
- **low**: eligible but only one weaker support path; UI recommends source verification;
- **none**: no eligible evidence; refuse.

Confidence is conservative across claims, not across unrelated retrieved chunks. Rejected candidates never lower confidence because they never enter citations.

## Answer Construction

### Extractive fact path

Single-slot relations use deterministic fact extraction when structured evidence exists:

- definition;
- title;
- author/advisor;
- position;
- date;
- simple identity facts.

The response template uses only the extracted fact and its citation. This path prevents the model from expanding beyond evidence.

### Grounded generation path

Responsibilities, lists, and multi-fact questions use the local chat model with only eligible evidence. The system prompt requires every factual clause to cite a provided evidence number and prohibits outside knowledge.

If the model is unavailable, the system may return an extractive evidence summary when the query contract supports it. It must not fabricate fluent prose from no evidence.

### Post-generation validation

Before persistence:

- every citation must still be live and owner-scoped;
- every cited number must exist;
- each answer factual clause must have a supporting citation for grounded-generation responses;
- forbidden or deleted document IDs are removed;
- if support disappears, refuse instead of saving the unsupported answer.

## Observability

Every query receives a retrieval trace ID. Structured logs record, without storing secret credentials:

- parsed query contract;
- active document scope;
- lane ranks;
- candidate signal values;
- eligibility decision and rejection reasons;
- deduplication decisions;
- selected evidence and final confidence;
- answer path: extractive, grounded model, or refusal.

A development-only diagnostic response or endpoint may expose the same trace to authorized users. Normal chat responses do not reveal internal scores beyond the existing confidence presentation.

## Evaluation Corpus

Create a versioned JSONL evaluation set derived from real and synthetic fixtures. Each case includes:

```json
{
  "id": "resume-fastgpt-definition",
  "question": "FastGPT是什么",
  "answerable": true,
  "expected_document_ids": ["resume"],
  "forbidden_document_ids": ["thesis"],
  "required_text": ["AI Agent 平台"],
  "relation": "definition",
  "critical": true
}
```

Coverage includes:

- FastGPT definition, position, responsibilities, and technology attributes;
- company responsibilities;
- thesis title, author, advisor, major, school, and completion date;
- multi-line cover fields;
- unsupported requirement-review roles;
- semantically similar but irrelevant thesis paragraphs;
- duplicate chunks and multiple documents;
- selected-document scope;
- owner isolation;
- tombstoned documents;
- parser failures and low-confidence OCR.

## Merge-Blocking Metrics

The evaluation runner reports retrieval, evidence, and answer metrics separately.

### Hard invariants

- critical known-fact Recall@10: `100%`;
- critical final-evidence document precision: `100%`;
- owner, selected-document, deletion, and active-version scope accuracy: `100%`;
- every citation resolves to live source lineage: `100%`;
- the FastGPT cases cite only the resume: `100%`;
- the unsupported requirement-review case produces no citations and refuses: `100%`.

### Corpus SLOs

- answerable-query Recall@10: at least `95%`;
- final citation precision: at least `95%`;
- unanswerable-query correct-refusal rate: at least `95%`;
- duplicate final-evidence rate: at most `2%`;
- parser meaningful-page coverage: `100%` or an explicit accepted exclusion reason.

Any hard-invariant failure or SLO regression blocks merge. Metrics are evaluated against a fixed corpus version so threshold changes cannot hide regressions.

## Rebuild and Rollout

The new chunk payload is incompatible with old generations. In demo mode:

1. parse and validate a complete new generation from the original MinIO object;
2. compute page coverage and structured facts;
3. index all new chunks and verify counts;
4. run document-level critical probes where available;
5. atomically switch the catalog version;
6. remove the old generation.

If parsing, coverage, embedding, or verification fails before the switch, the previous ready version remains active. After the feature is deployed, all current demo documents are rebuilt; mixed generations are not served.

## Error Handling

- Catalog or vector-store failure returns unavailable, never an ungrounded answer.
- Parser coverage failure marks rebuild failed and preserves the old version.
- Query-contract uncertainty falls back to the stricter general eligibility rules.
- Optional reranker or query-enhancement failure falls back to deterministic retrieval.
- Empty eligible evidence produces a refusal with a machine-readable reason.
- Trace logging failure does not alter retrieval decisions but is surfaced operationally.

## Testing Strategy

Development follows test-driven slices.

### Parsing tests

- thesis cover headings and key-value rows survive chunking;
- multi-line title values are reconstructed;
- meaningful pages cannot silently produce zero chunks;
- decorative repeated margins remain excluded;
- resume semantic relationships remain intact.

### Query-contract tests

- positive and negative patterns for every relation;
- FastGPT retains exact entity identity;
- `是什么` maps to definition;
- `有哪些关键角色` does not become evidence without concept support;
- title queries target thesis metadata facts.

### Retrieval and eligibility tests

- low-dense exact definition evidence is eligible;
- high-dense no-entity evidence is ineligible for named-entity queries;
- dense-only generic similarity cannot answer unsupported questions;
- structured title facts outrank body paragraphs;
- duplicate semantic units collapse;
- optional model failures do not change deterministic eligibility.

### End-to-end tests

- rebuild the real thesis and verify its title fact exists;
- rebuild the real resume and verify the FastGPT definition exists;
- run the versioned evaluation corpus through actual Qdrant and embeddings;
- verify final answer text, citation documents, refusal behavior, and scope isolation.

## Acceptance Criteria

1. `FastGPT是什么` answers only the source-supported definition and cites only `孟哲简历.pdf` page 1.
2. `在FastGPT负责什么岗位` cites the resume once and returns `全栈研发`.
3. `在珠海环届云有限公司负责什么` returns only the matching resume experience evidence.
4. `我的毕业论文题目是什么` returns `智能旅游规划助手设计与实现` from a page-1 metadata citation.
5. `新版本需求评审需要哪些关键角色` refuses and returns no citations for the current corpus.
6. No named-entity question cites a document without that entity or an explicit alias.
7. No meaningful PDF page disappears from the index without an explicit exclusion reason.
8. Duplicate same-unit citations are not shown.
9. All hard invariants and corpus SLOs pass on the rebuilt current corpus.
10. Existing deletion, owner isolation, selected-document scope, version switch, and unavailable-service behavior remain green.

## Deferred Work

- external web knowledge augmentation;
- automatic LLM-created entity aliases;
- a production distributed lexical engine for very large corpora;
- cross-encoder-driven eligibility, because eligibility must remain deterministic;
- multilingual relation patterns beyond the current Chinese/English corpus;
- continuous human relevance labeling UI.
