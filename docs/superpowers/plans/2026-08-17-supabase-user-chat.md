# Supabase User Isolation and Persistent Chat Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Supabase email/password authentication while keeping documents, files, vectors, conversations, messages, and authorization in local services with strict per-user isolation.

**Architecture:** Next.js owns browser sessions and proxies the Supabase access token to FastAPI. FastAPI independently verifies the JWT, derives the owner UUID from `sub`, and applies it to every PostgreSQL, MinIO, and Qdrant operation. PostgreSQL persists chat history and rolling summaries; the query pipeline combines a bounded recent window, a compact summary, and owner-filtered evidence.

**Tech Stack:** Next.js 15, React 19, `@supabase/ssr`, Supabase Auth, FastAPI, PyJWT, psycopg 3, PostgreSQL, MinIO, Qdrant, Ollama, pytest, Vitest.

## Global Constraints

- Supabase stores authentication and lightweight profile metadata only.
- Local PostgreSQL stores all document metadata, chat data, ownership, and index relationships.
- Local MinIO stores original files and parsed Markdown.
- Local Qdrant stores vectors and must filter every search by the JWT-derived `owner_id`.
- First release supports email/password sign-up, sign-in, and sign-out only.
- Default chat scope is all ready documents owned by the user; a conversation can select an owned subset.
- Keep the latest 6 turns verbatim and summarize older history to 600–1000 Chinese characters when it exceeds budget.
- Do not add sharing, admin workflows, deletion, message editing, streaming, OAuth, SMS, or password recovery.
- Preserve unrelated existing workspace changes.

---

### Task 1: JWT Identity Boundary

**Files:**
- Modify: `services/python-rag/requirements.txt`
- Modify: `services/python-rag/app/settings.py`
- Create: `services/python-rag/app/auth.py`
- Create: `services/python-rag/tests/test_auth.py`
- Modify: `.env.example`
- Modify: `docker-compose.yml`

**Interfaces:**
- Produces: `AuthenticatedUser(id: UUID, email: str | None, display_name: str | None)`.
- Produces: `require_user(credentials: HTTPAuthorizationCredentials) -> AuthenticatedUser` FastAPI dependency.
- Produces: settings `supabase_url`, `supabase_jwt_audience`, and derived JWKS URL.

- [ ] **Step 1: Write failing authentication tests**

```python
def test_require_user_returns_subject_from_valid_claims(monkeypatch):
    monkeypatch.setattr(verifier, "decode", lambda token: {
        "sub": "11111111-1111-1111-1111-111111111111",
        "email": "a@example.com",
        "user_metadata": {"display_name": "A"},
    })
    user = verifier.authenticate("valid")
    assert str(user.id) == "11111111-1111-1111-1111-111111111111"

def test_require_user_rejects_missing_subject(monkeypatch):
    monkeypatch.setattr(verifier, "decode", lambda token: {})
    with pytest.raises(HTTPException) as exc:
        verifier.authenticate("invalid")
    assert exc.value.status_code == 401
```

- [ ] **Step 2: Run `pytest tests/test_auth.py -q` and confirm it fails because `app.auth` is absent**
- [ ] **Step 3: Implement JWKS-backed verification using `jwt.PyJWKClient`, issuer `${SUPABASE_URL}/auth/v1`, audience `authenticated`, expiry validation, and UUID parsing**
- [ ] **Step 4: Add `PyJWT[crypto]==2.10.1`, Supabase environment variables, then rerun the test and confirm it passes**
- [ ] **Step 5: Commit only Task 1 files with `feat: verify supabase identities in rag api`**

### Task 2: Owner-Aware Local Persistence

**Files:**
- Create: `services/python-rag/migrations/001_user_chat.sql`
- Modify: `services/python-rag/app/models.py`
- Modify: `services/python-rag/app/document_catalog.py`
- Create: `services/python-rag/app/chat_catalog.py`
- Create: `services/python-rag/tests/test_document_ownership.py`
- Create: `services/python-rag/tests/test_chat_catalog.py`

**Interfaces:**
- Produces: `DocumentCatalog.upsert_user(user)`, `upsert(record, owner_id)`, `list_documents(owner_id)`, and `get(document_id, owner_id)`.
- Produces: `ChatCatalog.create_conversation(owner_id)`, `list_conversations(owner_id)`, `get_conversation(id, owner_id)`, `set_documents(id, owner_id, document_ids)`, `start_turn(...)`, and `finish_turn(...)`.
- Produces: Pydantic `ConversationSummary`, `ConversationDetail`, and `ChatMessage` response models.

- [ ] **Step 1: Write failing repository tests with a fake psycopg connection that assert every document query includes `owner_id` and cross-owner lookups return `None`**
- [ ] **Step 2: Run the two repository test modules and confirm expected failures for missing owner-aware methods**
- [ ] **Step 3: Add idempotent SQL for `app_users`, nullable legacy `rag_documents.owner_id`, the new-write guard trigger, `chat_conversations`, `chat_messages`, `conversation_documents`, constraints, and owner indexes**
- [ ] **Step 4: Implement focused catalogs whose public methods require an owner UUID and never expose unscoped query methods**
- [ ] **Step 5: Rerun repository tests and confirm they pass**
- [ ] **Step 6: Commit Task 2 files with `feat: persist owner-scoped documents and chats`**

### Task 3: Enforce Ownership Across Upload, Files, and Vectors

**Files:**
- Modify: `services/python-rag/app/main.py`
- Modify: `services/python-rag/app/vector_store.py`
- Modify: `services/python-rag/app/retrieval.py`
- Modify: `services/python-rag/app/pipeline.py`
- Modify: `services/python-rag/app/models.py`
- Modify: `services/python-rag/tests/test_upload.py`
- Modify: `services/python-rag/tests/test_document_detail.py`
- Create: `services/python-rag/tests/test_vector_ownership.py`

**Interfaces:**
- Consumes: `AuthenticatedUser` and owner-aware catalogs from Tasks 1–2.
- Produces: `IndexRequest.owner_id: UUID`.
- Produces: `VectorStore.search(question, owner_id, document_ids=None)` and owner-filtered point payloads.

- [ ] **Step 1: Update endpoint tests to override `require_user`, then add failing assertions that MinIO keys start with `users/{owner_id}/` and index requests carry the owner**
- [ ] **Step 2: Add a failing vector test asserting the Qdrant filter always contains `owner_id`, including when `document_ids` is empty**
- [ ] **Step 3: Run the focused tests and confirm they fail on the current global behavior**
- [ ] **Step 4: Require authentication on upload/list/detail/original/query/index; scope PostgreSQL queries and use owner-prefixed MinIO keys**
- [ ] **Step 5: Store `owner_id` in Qdrant payloads and combine `MatchValue(owner_id)` with optional `MatchAny(document_id)` filters**
- [ ] **Step 6: Reject selected document IDs unless all resolve to the current owner before retrieval**
- [ ] **Step 7: Run focused tests and the full Python suite; confirm all pass**
- [ ] **Step 8: Commit Task 3 files with `feat: isolate documents and vectors by owner`**

### Task 4: Persistent Conversations and Bounded Context

**Files:**
- Create: `services/python-rag/app/chat_context.py`
- Modify: `services/python-rag/app/graph.py`
- Modify: `services/python-rag/app/main.py`
- Modify: `services/python-rag/app/ollama.py`
- Modify: `services/python-rag/app/models.py`
- Create: `services/python-rag/tests/test_chat_context.py`
- Create: `services/python-rag/tests/test_chat_endpoints.py`

**Interfaces:**
- Produces: `ChatContextBuilder.build(summary, messages, question) -> ChatContext` containing `recent_messages`, `retrieval_query`, and bounded prompt text.
- Produces: conversation list/create/detail/update endpoints and `POST /rag/conversations/{id}/messages`.
- Extends: `run_query(question, owner_id, document_ids, conversation_context, strategy)`.

- [ ] **Step 1: Write failing context tests showing the newest 12 messages are verbatim, older messages are excluded after summary, and retrieval query includes the latest two user messages**
- [ ] **Step 2: Write failing endpoint tests for empty new chat, owner-only history, successful message persistence with citation snapshots, and failed assistant status when generation raises**
- [ ] **Step 3: Run the focused tests and verify expected missing-feature failures**
- [ ] **Step 4: Implement deterministic title generation, transactional user/pending-assistant writes, completion/failure updates, and document-scope validation**
- [ ] **Step 5: Extend Ollama chat to accept a message list; compose system rule, rolling summary, recent messages, current question, and evidence without duplicating full history**
- [ ] **Step 6: Trigger rolling-summary generation only when unsummarized history exceeds 12 messages; clamp stored summaries to 1000 Chinese characters**
- [ ] **Step 7: Run focused and full Python tests; confirm pass**
- [ ] **Step 8: Commit Task 4 files with `feat: add persistent contextual chat`**

### Task 5: Supabase Session Layer and Auth UI

**Files:**
- Modify: `apps/web/package.json`
- Modify: `apps/web/package-lock.json`
- Create: `apps/web/lib/supabase/client.ts`
- Create: `apps/web/lib/supabase/server.ts`
- Create: `apps/web/lib/supabase/middleware.ts`
- Create: `apps/web/middleware.ts`
- Create: `apps/web/app/login/page.tsx`
- Create: `apps/web/app/login/actions.ts`
- Create: `apps/web/components/auth-form.tsx`
- Create: `apps/web/lib/auth.test.ts`

**Interfaces:**
- Produces: browser/server Supabase client factories.
- Produces: `getAccessToken()` and `requireAccessToken()` for API handlers.
- Produces: protected application routes and public `/login`.

- [ ] **Step 1: Add Vitest and write a failing test for missing session returning 401 and valid session returning its access token**
- [ ] **Step 2: Run `npm test -- lib/auth.test.ts` and confirm failure before implementation**
- [ ] **Step 3: Install `@supabase/supabase-js`, `@supabase/ssr`, Vitest, and jsdom; create cookie-safe browser/server clients and session-refresh middleware**
- [ ] **Step 4: Implement email/password sign-up, sign-in, and sign-out with Chinese validation and error messages**
- [ ] **Step 5: Protect the workspace while allowing `/login`; show a clear configuration message when Supabase environment variables are absent**
- [ ] **Step 6: Run tests and `npm run build`; confirm both pass**
- [ ] **Step 7: Commit Task 5 files with `feat: add supabase email authentication`**

### Task 6: Authenticated Next.js API Gateway

**Files:**
- Create: `apps/web/lib/rag-api.ts`
- Modify: `apps/web/app/api/query/route.ts`
- Modify: `apps/web/app/api/documents/route.ts`
- Modify: `apps/web/app/api/documents/upload/route.ts`
- Modify: `apps/web/app/api/documents/[id]/route.ts`
- Modify: `apps/web/app/api/documents/[id]/original/route.ts`
- Create: `apps/web/app/api/conversations/route.ts`
- Create: `apps/web/app/api/conversations/[id]/route.ts`
- Create: `apps/web/app/api/conversations/[id]/messages/route.ts`
- Create: `apps/web/lib/rag-api.test.ts`

**Interfaces:**
- Produces: `ragFetch(path, init)` that requires a server session, forwards only the validated Bearer token, preserves upstream status, and handles invalid JSON safely.

- [ ] **Step 1: Write failing tests for 401 without a session, Authorization forwarding, status preservation, and binary original-file forwarding**
- [ ] **Step 2: Run the focused tests and confirm failure because `ragFetch` is missing**
- [ ] **Step 3: Implement the shared gateway and migrate every route to it, preserving PDF Inspector preprocessing before authenticated upload**
- [ ] **Step 4: Remove any code path that accepts or forwards a client-supplied owner ID**
- [ ] **Step 5: Run gateway tests and the Next.js build; confirm pass**
- [ ] **Step 6: Commit Task 6 files with `feat: authenticate rag api gateway`**

### Task 7: Conversation Workspace and Correct Send Interaction

**Files:**
- Refactor: `apps/web/app/page.tsx`
- Create: `apps/web/components/workspace.tsx`
- Create: `apps/web/components/chat-sidebar.tsx`
- Create: `apps/web/components/chat-panel.tsx`
- Create: `apps/web/components/document-filter.tsx`
- Create: `apps/web/lib/chat-state.ts`
- Create: `apps/web/lib/chat-state.test.ts`

**Interfaces:**
- Produces: `ChatMessage`, `ConversationListItem`, and `ConversationDetail` TypeScript types.
- Produces: pure optimistic state helpers `appendPendingTurn`, `completePendingTurn`, and `failPendingTurn`.

- [ ] **Step 1: Write failing state tests proving send clears the input, keeps the user message, creates one pending assistant message, replaces only that pending message on success, and marks it failed on error**
- [ ] **Step 2: Run the focused tests and confirm missing-helper failures**
- [ ] **Step 3: Implement the pure state helpers, then rerun tests to green**
- [ ] **Step 4: Replace demo message/result state with real message arrays and render loading, completed, refused, unavailable, and failed states**
- [ ] **Step 5: Add history sidebar, current-conversation loading, new-chat action, active highlighting, logout, and race guards so stale responses cannot overwrite a newly selected conversation**
- [ ] **Step 6: Add the per-conversation document selector with default “全部我的已就绪文档” and persist selected IDs before querying**
- [ ] **Step 7: Remove demo documents and answers from authenticated production views; show genuine empty states**
- [ ] **Step 8: Run unit tests and `npm run build`; confirm pass**
- [ ] **Step 9: Commit Task 7 files with `feat: add chat history and new conversation flow`**

### Task 8: Configuration, Migration, and End-to-End Verification

**Files:**
- Modify: `.env.example`
- Modify: `README.md`
- Modify: `docker-compose.yml`
- Modify: `start_rag.py`
- Test: all Python and web test suites

**Interfaces:**
- Documents exact required values: `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, `SUPABASE_URL`, and `SUPABASE_JWT_AUDIENCE=authenticated`.

- [ ] **Step 1: Document Supabase email-auth setup, local SQL migration execution, legacy-data isolation, and required environment values without including secrets**
- [ ] **Step 2: Ensure container and local startup pass the same Supabase verification settings to the web and RAG services**
- [ ] **Step 3: Run `pytest -q` in `services/python-rag` and record the exact pass count**
- [ ] **Step 4: Run `npm test -- --run` and `npm run build` in `apps/web`; record exact results**
- [ ] **Step 5: Run `git diff --check` and inspect `git diff --stat` plus `git status --short` to ensure unrelated user files remain untouched**
- [ ] **Step 6: Verify the acceptance matrix: unauthenticated 401, cross-owner 404, owner-filtered Qdrant query, owner-prefixed MinIO key, empty new chat, restored history, bounded context, citation snapshot, and optional document subset**
- [ ] **Step 7: Commit remaining configuration and documentation with `docs: configure authenticated local rag`**
