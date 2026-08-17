# Retrieval Relevance Guard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent stale or irrelevant vector results from reaching answer generation, and stop the UI from presenting candidate chunks as high-confidence evidence.

**Architecture:** PostgreSQL remains the source of truth for active documents. Query execution scopes Qdrant searches to active document IDs, applies an explicit relevance policy before LangGraph answer generation, limits final evidence, and returns a server-computed confidence level. The web UI displays only persistent documents and renders the backend confidence state.

**Tech Stack:** Python 3, FastAPI, LangGraph, Qdrant, PostgreSQL, pytest, Next.js 15, TypeScript.

## Global Constraints

- Do not delete Qdrant data automatically during a read request.
- Do not claim the configured BGE reranker is active while Ollama exposes no working rerank endpoint.
- Preserve the existing `vector`, `mqe`, `hyde`, and `hybrid` request values.
- An unrelated query must refuse before the chat model is called.

---

### Task 1: Active document retrieval scope

**Files:**
- Modify: `services/python-rag/app/document_catalog.py`
- Modify: `services/python-rag/app/main.py`
- Test: `services/python-rag/tests/test_document_catalog.py`

**Interfaces:**
- Produces: `DocumentCatalog.ready_document_ids() -> list[str]`
- Consumes: the returned IDs as the default `/rag/query` document scope.

- [ ] Write a failing catalog test proving only `status=ready` document IDs are returned.
- [ ] Run the focused test and confirm the method is missing.
- [ ] Add `ready_document_ids()` using a parameter-free ordered PostgreSQL query.
- [ ] Update `/rag/query` to use the caller's document IDs when supplied, otherwise the active catalog IDs.
- [ ] Run the focused test and API tests.

### Task 2: Evidence relevance policy

**Files:**
- Create: `services/python-rag/app/evidence.py`
- Modify: `services/python-rag/app/settings.py`
- Modify: `services/python-rag/app/graph.py`
- Modify: `services/python-rag/app/models.py`
- Test: `services/python-rag/tests/test_evidence.py`
- Test: `services/python-rag/tests/test_graph.py`

**Interfaces:**
- Produces: `EvidencePolicy.filter(citations) -> EvidenceDecision`
- Produces: `EvidenceDecision(citations, confidence, reason)`.
- `confidence` is `high`, `medium`, `low`, or `none`.

- [ ] Write failing tests proving a top score below `0.52` is rejected and final evidence is capped at 6.
- [ ] Run the tests and confirm failure because `EvidencePolicy` does not exist.
- [ ] Implement a minimal score gate and evidence cap with configurable settings.
- [ ] Route `none` decisions to `refuse_answer` before calling Ollama.
- [ ] Add `confidence` to `QueryResponse`; return `none` for refusal and the policy result for answers.
- [ ] Run evidence and graph tests.

### Task 3: Remove demo-state contamination from the UI

**Files:**
- Modify: `apps/web/app/page.tsx`

**Interfaces:**
- Consumes: backend `confidence` from `/api/query`.
- Displays: actual submitted question, persistent documents, and confidence-specific wording.

- [ ] Remove `demoDocuments`, `demoCitations`, and `demoDetail` from runtime state.
- [ ] Store the last submitted question and render it instead of hard-coded copy.
- [ ] Stop appending demo documents to `/api/documents` results.
- [ ] Replace `citations.length > 0 => 回答置信度高` with backend confidence rendering.
- [ ] Build the Next.js application to catch TypeScript and rendering regressions.

### Task 4: End-to-end regression verification

**Files:**
- Modify when needed: existing test files only.

**Interfaces:**
- Input: unrelated question `新版本的需求评审，需要哪些关键角色参加？`
- Expected: `status=refused`, no generated thesis summary, no stale CET citation.

- [ ] Run all Python tests.
- [ ] Build the web app.
- [ ] Restart or reload the RAG API.
- [ ] Query the running API with the unrelated question and inspect status, reason, citations, and confidence.
- [ ] Query a thesis-related question and verify it still reaches answer generation with bounded citations.
