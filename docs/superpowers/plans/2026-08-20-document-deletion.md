# Document Deletion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an owner-scoped delete action that immediately revokes a document, removes all PostgreSQL references, MinIO objects, and Qdrant points, and prevents deleted sources from being cited again.

**Architecture:** Commit a permanent minimal tombstone and database reference revocation before attempting external cleanup. A dedicated idempotent deletion service then purges and verifies Qdrant and MinIO; catalog and final-answer liveness checks make deletion win against stale indexes and concurrent queries.

**Tech Stack:** Python 3.12, FastAPI, Pydantic 2, psycopg 3/PostgreSQL JSONB, MinIO Python SDK, Qdrant Python client, Next.js 15, React 19, TypeScript, Vitest, pytest.

**Spec:** `docs/superpowers/specs/2026-08-19-document-deletion-design.md`

## Global Constraints

- The tombstone is permanent and stores only `owner_id`, `document_id`, and `deleted_at`.
- Historical question and answer text remains; deleted citation payloads are removed.
- Logical revocation commits before MinIO or Qdrant cleanup begins.
- Every operation is scoped by authenticated `owner_id` plus exact `document_id`.
- The API never accepts an object-storage prefix from the browser.
- A successful response is returned only after MinIO and Qdrant absence checks pass.
- Repeating deletion for a same-owner tombstone is safe and resumes cleanup.
- Unknown and cross-owner document IDs return indistinguishable `404` responses.

## File Map

- Create `services/python-rag/migrations/002_document_deletion.sql`: tombstone table and deleted-citation message flag.
- Create `services/python-rag/app/database.py`: one ordered migration runner shared by both catalogs.
- Create `services/python-rag/app/document_deletion.py`: orchestration and partial-cleanup result semantics.
- Create `services/python-rag/tests/test_document_deletion.py`: catalog transaction and coordinator tests.
- Create `services/python-rag/tests/test_document_deletion_endpoint.py`: authenticated API behavior.
- Create `apps/web/components/document-delete-dialog.tsx`: accessible irreversible-delete confirmation.
- Create `apps/web/components/document-delete-dialog.test.tsx`: dialog interaction tests.
- Modify `services/python-rag/app/document_catalog.py`: migrations, tombstoning, liveness filters, and citation revocation.
- Modify `services/python-rag/app/chat_catalog.py`: shared migrations plus deleted-citation message transport.
- Modify `services/python-rag/app/object_storage.py`: exact-prefix purge and verification.
- Modify `services/python-rag/app/vector_store.py`: all-version purge and verification.
- Modify `services/python-rag/app/models.py`: deletion responses and deleted-citation message flag.
- Modify `services/python-rag/app/retrieval.py`: post-fusion candidate liveness validation.
- Modify `services/python-rag/app/main.py`: DELETE endpoint and final citation liveness validation.
- Modify `services/python-rag/app/chat_catalog.py`: read/write the deleted-citation flag.
- Modify `services/python-rag/tests/test_vector_store.py`: all-version filtered deletion tests.
- Modify `services/python-rag/tests/test_hybrid_retrieval.py`: stale candidate filtering test.
- Modify `services/python-rag/tests/test_chat_endpoints.py`: deletion race before persistence test.
- Modify `apps/web/app/api/documents/[id]/route.ts`: proxy DELETE as well as GET.
- Modify `apps/web/components/workspace.tsx`: deletion state, list action, retry, and state removal.
- Modify `apps/web/components/document-detail-view.tsx`: detail delete action.
- Modify `apps/web/components/chat-panel.tsx`: deleted-source notice.
- Modify `apps/web/lib/chat-state.ts`: transport type for `has_deleted_citations`.
- Modify associated existing React tests for list, detail, and chat behavior.

---

### Task 1: Tombstone Schema and Atomic Catalog Revocation

**Files:**
- Create: `services/python-rag/migrations/002_document_deletion.sql`
- Create: `services/python-rag/app/database.py`
- Create: `services/python-rag/tests/test_document_deletion.py`
- Modify: `services/python-rag/app/document_catalog.py`
- Modify: `services/python-rag/app/models.py`
- Modify: `services/python-rag/app/chat_catalog.py`

**Interfaces:**
- Produces: `DocumentCatalog.begin_delete(owner_id: UUID, document_id: str) -> bool`
- Produces: `DocumentCatalog.live_document_ids(owner_id: UUID, document_ids: list[str]) -> set[str]`
- Produces: `ChatMessage.has_deleted_citations: bool`
- Produces: `run_migrations(connect: Callable[[], Connection]) -> None`
- `begin_delete` returns `False` only for unknown/cross-owner IDs and `True` for a live document or same-owner tombstone retry.

- [ ] **Step 1: Write failing migration and catalog tests**

Use a recording fake connection to assert transaction SQL and returned behavior without requiring a live PostgreSQL server:

```python
def test_begin_delete_tombstones_before_removing_catalog(monkeypatch):
    catalog, conn = recording_catalog(monkeypatch, live_owner=OWNER)

    assert catalog.begin_delete(OWNER, "doc-1") is True
    sql = "\n".join(conn.statements)
    assert sql.index("INSERT INTO rag_document_tombstones") < sql.index("DELETE FROM rag_documents")
    assert "jsonb_array_elements" in sql
    assert "has_deleted_citations = true" in sql


def test_begin_delete_accepts_same_owner_tombstone_retry(monkeypatch):
    catalog, _ = recording_catalog(monkeypatch, tombstone_owner=OWNER)
    assert catalog.begin_delete(OWNER, "doc-1") is True


def test_begin_delete_hides_cross_owner_document(monkeypatch):
    catalog, conn = recording_catalog(monkeypatch, live_owner=OTHER_OWNER)
    assert catalog.begin_delete(OWNER, "doc-1") is False
    assert not any("DELETE FROM rag_documents" in item for item in conn.statements)
```

- [ ] **Step 2: Run the focused tests and verify failure**

Run from `services/python-rag`:

```powershell
python -m pytest tests/test_document_deletion.py -q
```

Expected: FAIL because the migration and `begin_delete`/`live_document_ids` methods do not exist.

- [ ] **Step 3: Add the migration and make schema loading ordered**

Create `002_document_deletion.sql`:

```sql
CREATE TABLE IF NOT EXISTS rag_document_tombstones (
    document_id text PRIMARY KEY,
    owner_id uuid NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
    deleted_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS rag_document_tombstones_owner_idx
    ON rag_document_tombstones (owner_id, deleted_at DESC);
ALTER TABLE chat_messages
    ADD COLUMN IF NOT EXISTS has_deleted_citations boolean NOT NULL DEFAULT false;
```

Create a shared runner and call it from both `DocumentCatalog.ensure_schema()` and `ChatCatalog.ensure_schema()` so either API surface safely upgrades an existing installation:

```python
def run_migrations(connect) -> None:
    directory = Path(__file__).resolve().parents[1] / "migrations"
    with connect() as conn:
        for migration in sorted(directory.glob("*.sql")):
            conn.execute(migration.read_text(encoding="utf-8"))
```

- [ ] **Step 4: Implement the atomic revocation transaction**

Implement `begin_delete` with explicit owner checks, then insert the tombstone before running the citation rewrite and deletions:

```python
def begin_delete(self, owner_id: UUID, document_id: str) -> bool:
    self.ensure_schema()
    with self._connect() as conn:
        live = conn.execute(
            "SELECT owner_id FROM rag_documents WHERE document_id = %s FOR UPDATE",
            (document_id,),
        ).fetchone()
        tombstone = conn.execute(
            "SELECT owner_id FROM rag_document_tombstones WHERE document_id = %s",
            (document_id,),
        ).fetchone()
        if live and live["owner_id"] != owner_id:
            return False
        if not live and (not tombstone or tombstone["owner_id"] != owner_id):
            return False
        conn.execute(
            """INSERT INTO rag_document_tombstones (document_id, owner_id)
               VALUES (%s, %s) ON CONFLICT (document_id) DO NOTHING""",
            (document_id, owner_id),
        )
        conn.execute(CITATION_REVOCATION_SQL, (document_id, owner_id, document_id))
        conn.execute(
            "DELETE FROM conversation_documents WHERE owner_id = %s AND document_id = %s",
            (owner_id, document_id),
        )
        conn.execute(
            "DELETE FROM rag_document_index_reservations WHERE owner_id = %s AND document_id = %s",
            (owner_id, document_id),
        )
        conn.execute(
            "DELETE FROM rag_documents WHERE owner_id = %s AND document_id = %s",
            (owner_id, document_id),
        )
    return True
```

Use a JSONB subquery that preserves nonmatching citations and `COALESCE`s an empty result to `'[]'::jsonb`. For `upsert` and `finalize_index`, change `INSERT ... VALUES` to `INSERT ... SELECT ... WHERE NOT EXISTS (SELECT 1 FROM rag_document_tombstones ...)`; an `ON CONFLICT ... WHERE` clause alone cannot block reinsertion after the live row has been deleted. Add the same tombstone exclusion to `reserve_index_version`, `ready_document_scopes`, `list_documents`, and `get`.

- [ ] **Step 5: Add message transport and live-ID filtering**

Add `has_deleted_citations: bool = False` to `ChatMessage`, include it in every `chat_catalog.py` message SELECT/RETURNING statement, and implement:

```python
def live_document_ids(self, owner_id: UUID, document_ids: list[str]) -> set[str]:
    if not document_ids:
        return set()
    with self._connect() as conn:
        rows = conn.execute(
            """SELECT d.document_id FROM rag_documents d
               WHERE d.owner_id = %s AND d.status = 'ready'
                 AND d.document_id = ANY(%s)
                 AND NOT EXISTS (
                   SELECT 1 FROM rag_document_tombstones t
                   WHERE t.document_id = d.document_id
                 )""",
            (owner_id, document_ids),
        ).fetchall()
    return {row["document_id"] for row in rows}
```

- [ ] **Step 6: Run catalog and chat regression tests**

```powershell
python -m pytest tests/test_document_deletion.py tests/test_chat_catalog.py tests/test_document_ownership.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit the database slice**

```powershell
git add services/python-rag/migrations/002_document_deletion.sql services/python-rag/app/database.py services/python-rag/app/document_catalog.py services/python-rag/app/models.py services/python-rag/app/chat_catalog.py services/python-rag/tests/test_document_deletion.py
git commit -m "feat: revoke deleted documents atomically"
```

### Task 2: Exact-Prefix MinIO Purge and All-Version Qdrant Purge

**Files:**
- Modify: `services/python-rag/app/object_storage.py`
- Modify: `services/python-rag/app/vector_store.py`
- Modify: `services/python-rag/tests/test_vector_store.py`
- Modify: `services/python-rag/tests/test_document_deletion.py`

**Interfaces:**
- Produces: `ObjectStorage.delete_document(owner_id: UUID, document_id: str) -> None`
- Produces: `ObjectStorage.document_exists(owner_id: UUID, document_id: str) -> bool`
- Produces: `VectorStore.delete_document(owner_id: UUID, document_id: str) -> None`
- Produces: `VectorStore.document_exists(owner_id: UUID, document_id: str) -> bool`

- [ ] **Step 1: Write failing storage-scope tests**

```python
def test_object_storage_deletes_only_exact_document_prefix(fake_minio):
    storage = storage_with(fake_minio)
    storage.delete_document(OWNER, "doc-1")
    assert fake_minio.list_prefix == f"users/{OWNER}/documents/doc-1/"
    assert fake_minio.recursive is True


def test_vector_store_deletes_every_version_for_owner_and_document(fake_qdrant):
    store = vector_store_with(fake_qdrant)
    store.delete_document(OWNER, "doc-1")
    selector = fake_qdrant.deleted_selector
    assert filter_values(selector.filter) == {"owner_id": str(OWNER), "document_id": "doc-1"}
    assert "version" not in filter_values(selector.filter)
```

- [ ] **Step 2: Run the tests and verify failure**

```powershell
python -m pytest tests/test_document_deletion.py tests/test_vector_store.py -q
```

Expected: FAIL because all-version deletion and absence checks do not exist.

- [ ] **Step 3: Implement safe MinIO prefix deletion and verification**

Keep prefix construction private and derived from typed IDs:

```python
@staticmethod
def _document_prefix(owner_id: UUID, document_id: str) -> str:
    if not document_id or "/" in document_id or "\\" in document_id:
        raise ValueError("invalid document id")
    return f"users/{owner_id}/documents/{document_id}/"

def delete_document(self, owner_id: UUID, document_id: str) -> None:
    objects = self.client.list_objects(
        self.bucket, prefix=self._document_prefix(owner_id, document_id), recursive=True
    )
    errors = list(self.client.remove_objects(
        self.bucket, (DeleteObject(item.object_name) for item in objects)
    ))
    if errors:
        raise RuntimeError("MinIO document purge failed")

def document_exists(self, owner_id: UUID, document_id: str) -> bool:
    return next(iter(self.client.list_objects(
        self.bucket, prefix=self._document_prefix(owner_id, document_id), recursive=True
    )), None) is not None
```

- [ ] **Step 4: Implement Qdrant all-version deletion and verification**

Factor the owner/document filter into `_document_filter` and use it for delete plus a one-item scroll:

```python
def delete_document(self, owner_id: UUID, document_id: str) -> None:
    self.client.delete(
        COLLECTION,
        points_selector=FilterSelector(filter=self._document_filter(owner_id, document_id)),
        wait=True,
    )

def document_exists(self, owner_id: UUID, document_id: str) -> bool:
    points, _ = self.client.scroll(
        COLLECTION,
        scroll_filter=self._document_filter(owner_id, document_id),
        limit=1,
        with_payload=False,
        with_vectors=False,
    )
    return bool(points)
```

Treat a missing Qdrant collection as an empty store in both methods, so deletion remains idempotent before the first upload.

- [ ] **Step 5: Run storage tests**

```powershell
python -m pytest tests/test_document_deletion.py tests/test_vector_store.py tests/test_vector_ownership.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit the storage slice**

```powershell
git add services/python-rag/app/object_storage.py services/python-rag/app/vector_store.py services/python-rag/tests/test_document_deletion.py services/python-rag/tests/test_vector_store.py
git commit -m "feat: purge document storage and vectors"
```

### Task 3: Idempotent Deletion Coordinator and API

**Files:**
- Create: `services/python-rag/app/document_deletion.py`
- Create: `services/python-rag/tests/test_document_deletion_endpoint.py`
- Modify: `services/python-rag/app/models.py`
- Modify: `services/python-rag/app/main.py`
- Modify: `services/python-rag/tests/test_document_deletion.py`

**Interfaces:**
- Produces: `DocumentDeletionService.delete(owner_id: UUID, document_id: str) -> DocumentDeleteResponse`
- Produces: `DELETE /rag/documents/{document_id}`
- Produces: `DocumentDeleteResponse(document_id, status, tombstoned, objects_remaining, vectors_remaining)`

- [ ] **Step 1: Write failing coordinator tests**

```python
def test_delete_revokes_before_external_purge():
    events = []
    service = deletion_service(events=events)
    result = service.delete(OWNER, "doc-1")
    assert events == ["tombstone", "vectors-delete", "objects-delete", "vectors-check", "objects-check"]
    assert result.status == "deleted"


def test_delete_reports_pending_but_keeps_tombstone_on_storage_failure():
    service = deletion_service(object_error=RuntimeError("offline"))
    with pytest.raises(DocumentPurgePending) as raised:
        service.delete(OWNER, "doc-1")
    assert raised.value.result.tombstoned is True
    assert raised.value.result.status == "purge_pending"
```

- [ ] **Step 2: Run focused tests and verify failure**

```powershell
python -m pytest tests/test_document_deletion.py tests/test_document_deletion_endpoint.py -q
```

Expected: FAIL because the coordinator, response model, exception, and route do not exist.

- [ ] **Step 3: Implement response model and coordinator**

```python
class DocumentDeleteResponse(BaseModel):
    document_id: str
    status: Literal["deleted", "purge_pending"]
    tombstoned: bool = True
    objects_remaining: bool
    vectors_remaining: bool


class DocumentPurgePending(RuntimeError):
    def __init__(self, result: DocumentDeleteResponse):
        self.result = result
        super().__init__("document purge pending")


def delete(self, owner_id: UUID, document_id: str) -> DocumentDeleteResponse:
    if not self.catalog.begin_delete(owner_id, document_id):
        raise DocumentNotFound(document_id)
    try:
        self.vectors.delete_document(owner_id, document_id)
        self.objects.delete_document(owner_id, document_id)
        vectors_remaining = self.vectors.document_exists(owner_id, document_id)
        objects_remaining = self.objects.document_exists(owner_id, document_id)
    except Exception as exc:
        raise DocumentPurgePending(self._probe(owner_id, document_id)) from exc
    result = DocumentDeleteResponse(
        document_id=document_id,
        status="purge_pending" if vectors_remaining or objects_remaining else "deleted",
        objects_remaining=objects_remaining,
        vectors_remaining=vectors_remaining,
    )
    if result.status == "purge_pending":
        raise DocumentPurgePending(result)
    return result
```

`_probe` catches failures per store and conservatively reports the failed store as remaining.

- [ ] **Step 4: Add the authenticated DELETE endpoint**

```python
@app.delete("/rag/documents/{document_id}", response_model=DocumentDeleteResponse)
async def delete_document(document_id: str, user: AuthenticatedUser = Depends(require_user)):
    try:
        return document_deletion.delete(user.id, document_id)
    except DocumentNotFound as exc:
        raise HTTPException(404, "Document not found") from exc
    except DocumentPurgePending as exc:
        return JSONResponse(status_code=503, content=exc.result.model_dump())
```

- [ ] **Step 5: Test authentication, ownership, success, pending, and retry**

```python
def test_delete_endpoint_returns_503_safe_shape_for_pending_cleanup(client, monkeypatch):
    install_pending_deletion(monkeypatch)
    response = client.delete("/rag/documents/doc-1", headers=auth_headers(OWNER))
    assert response.status_code == 503
    assert response.json() == {
        "document_id": "doc-1", "status": "purge_pending", "tombstoned": True,
        "objects_remaining": True, "vectors_remaining": False,
    }
    assert "offline" not in response.text
```

Run:

```powershell
python -m pytest tests/test_document_deletion.py tests/test_document_deletion_endpoint.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit the service and endpoint slice**

```powershell
git add services/python-rag/app/document_deletion.py services/python-rag/app/models.py services/python-rag/app/main.py services/python-rag/tests/test_document_deletion.py services/python-rag/tests/test_document_deletion_endpoint.py
git commit -m "feat: expose idempotent document deletion"
```

### Task 4: Retrieval and Answer-Time Citation Revocation

**Files:**
- Modify: `services/python-rag/app/retrieval.py`
- Modify: `services/python-rag/app/main.py`
- Modify: `services/python-rag/tests/test_hybrid_retrieval.py`
- Modify: `services/python-rag/tests/test_chat_endpoints.py`

**Interfaces:**
- Consumes: `DocumentCatalog.live_document_ids(owner_id, document_ids)` from Task 1.
- Produces: only live citations from `MultiStrategyRetriever.retrieve` and immediately before `finish_turn`.

- [ ] **Step 1: Write failing stale-candidate tests**

```python
def test_hybrid_retrieval_drops_candidate_deleted_after_scope_load():
    catalog = RaceCatalog(scopes=[("doc-1", 1)], live_ids=set())
    retriever = MultiStrategyRetriever(store=StaleStore(), catalog=catalog, lexical=NoLexical())
    citations = asyncio.run(retriever.retrieve("问题", OWNER, strategy="hybrid"))
    assert citations == []


def test_chat_rechecks_citations_before_persistence(client, monkeypatch):
    install_query_result(monkeypatch, citations=[citation("doc-1")])
    install_live_ids(monkeypatch, set())
    response = client.post(message_url(), json={"question": "问题"}, headers=auth_headers(OWNER))
    assert response.status_code == 200
    assert saved_assistant().citations == []
```

- [ ] **Step 2: Run tests and verify failure**

```powershell
python -m pytest tests/test_hybrid_retrieval.py tests/test_chat_endpoints.py -q
```

Expected: FAIL because stale candidates are currently returned and persisted.

- [ ] **Step 3: Filter fused retrieval output against the live catalog**

At the end of `retrieve`, after fusion/reranking and before returning:

```python
ranked = sorted(items.values(), key=lambda item: item.rrf_score or 0, reverse=True)
live_ids = self.catalog.live_document_ids(
    owner_id, list(dict.fromkeys(item.document_id for item in ranked))
)
return [item for item in ranked if item.document_id in live_ids]
```

If the final liveness query fails, raise `CatalogUnavailableError`; never fail open to stale citations.

- [ ] **Step 4: Recheck immediately before chat persistence**

Add a helper in `main.py`:

```python
def live_citations(owner_id: UUID, citations: list[Citation]) -> list[Citation]:
    if not citations:
        return []
    live = document_catalog.live_document_ids(
        owner_id, list(dict.fromkeys(item.document_id for item in citations))
    )
    return [item for item in citations if item.document_id in live]
```

Call it after `run_query` and before `finish_turn`. When every citation disappears from an otherwise answered result, persist the existing evidence-refusal copy with `confidence="none"` instead of the generated answer, so unsupported text is not left behind with no source.

- [ ] **Step 5: Run retrieval, graph, and endpoint tests**

```powershell
python -m pytest tests/test_hybrid_retrieval.py tests/test_query_scope.py tests/test_graph.py tests/test_chat_endpoints.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit race protection**

```powershell
git add services/python-rag/app/retrieval.py services/python-rag/app/main.py services/python-rag/tests/test_hybrid_retrieval.py services/python-rag/tests/test_chat_endpoints.py
git commit -m "fix: prevent citations from deleted documents"
```

### Task 5: Web Proxy, Confirmation Dialog, and Document State Removal

**Files:**
- Create: `apps/web/components/document-delete-dialog.tsx`
- Create: `apps/web/components/document-delete-dialog.test.tsx`
- Modify: `apps/web/app/api/documents/[id]/route.ts`
- Modify: `apps/web/components/workspace.tsx`
- Modify: `apps/web/components/document-detail-view.tsx`
- Modify: `apps/web/components/workspace.test.tsx`
- Modify: `apps/web/components/document-detail-view.test.tsx`

**Interfaces:**
- Produces: `DocumentDeleteDialog({ documentName, open, busy, onCancel, onConfirm })`.
- Produces: `DELETE /api/documents/{id}` proxy.
- Produces: `DeleteResult` with the backend response fields from Task 3.

- [ ] **Step 1: Write failing dialog and workspace state tests**

```tsx
it("requires explicit confirmation and names the irreversible document", () => {
  render(<DocumentDeleteDialog documentName="简历.pdf" open busy={false} onCancel={cancel} onConfirm={confirm} />);
  expect(screen.getByText("简历.pdf")).toBeTruthy();
  expect(screen.getByText(/无法恢复/)).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "确认删除" }));
  expect(confirm).toHaveBeenCalledOnce();
});

it("removes a tombstoned document even when physical cleanup is pending", () => {
  const state = removeDeletedDocument(initialState, "doc-1");
  expect(state.documents).not.toContainEqual(expect.objectContaining({ document_id: "doc-1" }));
  expect(state.selectedDocumentIds).not.toContain("doc-1");
});
```

- [ ] **Step 2: Run web tests and verify failure**

Run from `apps/web`:

```powershell
pnpm test -- --run components/document-delete-dialog.test.tsx components/workspace.test.tsx components/document-detail-view.test.tsx
```

Expected: FAIL because the dialog, delete helper, and delete controls do not exist.

- [ ] **Step 3: Proxy DELETE while preserving upstream status**

Add to `[id]/route.ts`:

```ts
export async function DELETE(_request: Request, { params }: RouteContext) {
  const { id } = await params;
  const response = await ragFetch(`/rag/documents/${encodeURIComponent(id)}`, { method: "DELETE" });
  return new Response(await response.text(), {
    status: response.status,
    headers: { "content-type": response.headers.get("content-type") || "application/json" },
  });
}
```

- [ ] **Step 4: Implement an accessible confirmation dialog**

Use a fixed overlay with `role="dialog"`, `aria-modal="true"`, a heading referenced by `aria-labelledby`, Cancel, and destructive Confirm buttons. Disable both dismissal and confirmation while `busy` is true, and label the busy action `正在删除…`.

- [ ] **Step 5: Add workspace deletion state and retry behavior**

Track `{document_id, document_name}` as the pending target and one `deletingId`. On either `deleted` or a `503` payload with `tombstoned: true`, synchronously:

```ts
setDocuments(current => current.filter(item => item.document_id !== id));
setSelectedDocumentIds(current => current.filter(value => value !== id));
setDetail(current => current?.document_id === id ? null : current);
if (detail?.document_id === id) setView("documents");
```

For `purge_pending`, keep `{id, name}` in retry notice state and render a `重试清理` button that sends the same DELETE request. For failures without `tombstoned: true`, leave document state unchanged.

Pass `onDelete` to both `DocumentsView` and `DocumentDetailView`; place `删除` next to `查看` in the table and in the detail header.

- [ ] **Step 6: Run component tests**

```powershell
pnpm test -- --run components/document-delete-dialog.test.tsx components/workspace.test.tsx components/document-detail-view.test.tsx
```

Expected: PASS.

- [ ] **Step 7: Commit the web deletion workflow**

```powershell
git add apps/web/app/api/documents/[id]/route.ts apps/web/components/document-delete-dialog.tsx apps/web/components/document-delete-dialog.test.tsx apps/web/components/workspace.tsx apps/web/components/workspace.test.tsx apps/web/components/document-detail-view.tsx apps/web/components/document-detail-view.test.tsx
git commit -m "feat: add document deletion controls"
```

### Task 6: Deleted-Citation Notice in Historical Chat

**Files:**
- Modify: `apps/web/lib/chat-state.ts`
- Modify: `apps/web/components/chat-panel.tsx`
- Modify: `apps/web/components/chat-panel.test.tsx`

**Interfaces:**
- Consumes: `ChatMessage.has_deleted_citations` from Task 1.
- Produces: visible copy `原资料已删除，相关引用已移除。` on affected messages.

- [ ] **Step 1: Write the failing rendering test**

```tsx
it("explains when historical citations were removed", () => {
  renderPanel([{ ...assistantMessage, citations: [], has_deleted_citations: true }]);
  expect(screen.getByText("原资料已删除，相关引用已移除。")).toBeTruthy();
});
```

Also test that a message with one surviving citation and the flag renders both the notice and citation details.

- [ ] **Step 2: Run the focused test and verify failure**

```powershell
pnpm test -- --run components/chat-panel.test.tsx
```

Expected: FAIL because the transport type and notice are absent.

- [ ] **Step 3: Add the transport field and notice**

Add `has_deleted_citations?: boolean` to `ChatMessage`. Render below the answer body and before remaining citations:

```tsx
{message.has_deleted_citations && (
  <p className="mt-3 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
    原资料已删除，相关引用已移除。
  </p>
)}
```

- [ ] **Step 4: Run chat and state tests**

```powershell
pnpm test -- --run components/chat-panel.test.tsx lib/chat-state.test.ts
```

Expected: PASS.

- [ ] **Step 5: Commit the historical-chat notice**

```powershell
git add apps/web/lib/chat-state.ts apps/web/components/chat-panel.tsx apps/web/components/chat-panel.test.tsx
git commit -m "feat: mark citations removed with deleted documents"
```

### Task 7: Full Verification and Documentation Alignment

**Files:**
- Modify only if verification reveals a defect: files already listed in Tasks 1-6.
- Verify: `docs/superpowers/specs/2026-08-19-document-deletion-design.md`
- Verify: `docs/superpowers/plans/2026-08-20-document-deletion.md`

**Interfaces:**
- Consumes all previous task outputs.
- Produces a release-ready, fully tested deletion flow.

- [ ] **Step 1: Run the complete Python suite**

From `services/python-rag`:

```powershell
python -m pytest -q
```

Expected: all tests PASS.

- [ ] **Step 2: Run the complete web suite**

From `apps/web`:

```powershell
pnpm test -- --run
```

Expected: all tests PASS.

- [ ] **Step 3: Build production web assets**

```powershell
pnpm build
```

Expected: Next.js production build completes with no TypeScript or route-handler error.

- [ ] **Step 4: Build the Python service container**

From the repository root:

```powershell
docker compose build rag-api
```

Expected: image build succeeds.

- [ ] **Step 5: Perform a live smoke test when local services are available**

Upload a disposable document, attach it to a conversation, generate one cited answer, delete it, then verify:

```text
GET /rag/documents                         -> document absent
GET /rag/documents/{id}                    -> 404
GET /rag/documents/{id}/original           -> 404
conversation selected_document_ids         -> id absent
historical assistant citations             -> matching citation absent
historical assistant has_deleted_citations -> true
new query                                   -> never cites id
MinIO users/{owner}/documents/{id}/         -> empty
Qdrant owner_id + document_id filter        -> zero points
```

If local external services are unavailable, record that the automated fake-store verification passed and do not claim the live smoke test ran.

- [ ] **Step 6: Check formatting, scope, and accidental changes**

```powershell
git diff --check
git status --short
git diff --stat
```

Expected: no whitespace errors and only deletion-feature files changed.

- [ ] **Step 7: Commit verification-only fixes if any**

If verification required code changes, first add a regression test, make the focused test pass, rerun Steps 1-4, then commit only those fixes:

```powershell
git add services/python-rag apps/web
git commit -m "test: verify document deletion end to end"
```
