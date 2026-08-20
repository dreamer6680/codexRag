# Document Deletion and Citation Revocation Design

Date: 2026-08-19

## Goal

Add an owner-scoped document deletion action that removes the document from PostgreSQL, MinIO, and Qdrant. As soon as deletion begins, the document must stop participating in retrieval and must never appear in newly generated citations, even when physical cleanup partially fails or races with an in-flight rebuild or query.

Historical question and answer text remains available. Citations that refer to the deleted document are removed and the affected message displays that its original source was deleted.

## Chosen Approach

Use tombstone-first, idempotent hard deletion.

The system first commits a minimal deletion tombstone in PostgreSQL and revokes every database-visible reference. It then removes vector points and object-storage artifacts and verifies that they are gone. The tombstone is permanent and contains only `owner_id`, `document_id`, and `deleted_at`; it contains no filename, document text, chunk, vector, or citation content.

This ordering makes logical deletion atomic. MinIO or Qdrant can fail temporarily without making stale content searchable or citable. Repeating the same delete request resumes cleanup safely.

## Alternatives Considered

### Direct synchronous hard delete

Deleting PostgreSQL, MinIO, and Qdrant records without a tombstone is simpler, but the stores do not share a transaction. A partial failure can leave stale vectors searchable or allow an in-flight index publication to recreate the document.

### Soft delete while retaining content and indexes

A soft-delete flag gives fast UI behavior, but intentionally retains the source and index data. It does not meet the complete-deletion requirement and increases privacy risk.

## Data Model

Add a migration after `001_user_chat.sql` with:

```sql
CREATE TABLE rag_document_tombstones (
    document_id text PRIMARY KEY,
    owner_id uuid NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
    deleted_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX rag_document_tombstones_owner_idx
    ON rag_document_tombstones (owner_id, deleted_at DESC);

ALTER TABLE chat_messages
    ADD COLUMN has_deleted_citations boolean NOT NULL DEFAULT false;
```

`document_id` remains globally unique, matching the existing `rag_documents` primary-key model. The message flag contains no deleted citation content; it only lets the UI explain why a previously generated answer no longer has all its citations.

## Database Revocation Transaction

`DocumentCatalog.begin_delete(owner_id, document_id)` performs one transaction:

1. Lock the matching `rag_documents` row when it exists.
2. Validate ownership without revealing whether another user's document exists.
3. If the live row no longer exists, accept the request only when a tombstone with the same owner and document ID exists; this makes retries idempotent.
4. Insert the tombstone with `ON CONFLICT DO NOTHING`.
5. For every owner message whose citation array contains this `document_id`, remove the matching citation objects and set `has_deleted_citations = true`.
6. Delete `conversation_documents` associations. The existing foreign key also cascades these rows when the catalog row is removed.
7. Delete `rag_document_index_reservations` so an already reserved rebuild cannot be published.
8. Delete the `rag_documents` row.

The transaction commits before external cleanup starts. After commit, the normal document list, detail, original-file, conversation filter, and retrieval-scope queries can no longer return the document.

The citation rewrite uses `jsonb_array_elements` and rebuilds the array without objects whose `document_id` matches. It never rewrites the answer body.

## Race Protection

Deletion must also win against work that began before the tombstone was committed.

- `reserve_index_version`, `finalize_index`, and catalog `upsert` refuse a document ID present in `rag_document_tombstones`.
- `ready_document_scopes`, `list_documents`, and `get` explicitly exclude tombstones as defense in depth.
- Hybrid retrieval validates fused candidate document IDs against the live catalog immediately before evidence gating.
- The answer path validates final citations again immediately before model context construction and message persistence.
- If deletion commits during a model call, the final validation removes the citation and the answer path refuses or regenerates from the remaining live evidence rather than persisting a deleted source.

These checks protect against stale Qdrant points, an in-flight rebuild, and a query that loaded its scope immediately before deletion.

## Qdrant Cleanup

Add `VectorStore.delete_document(owner_id, document_id)` using a payload filter on both fields and without a version condition. This removes every index generation, including abandoned or partially built versions.

After deletion, verification performs a filtered count or one-item scroll. Cleanup succeeds only when no matching point remains. Repeating the operation is safe when the point set is already empty.

## MinIO Cleanup

Add `ObjectStorage.delete_prefix(prefix)` and `ObjectStorage.prefix_exists(prefix)`.

The exact prefix is derived rather than read from the deleted catalog row:

```text
users/{owner_id}/documents/{document_id}/
```

All objects below the prefix are listed recursively and removed. This includes original uploads, parsed Markdown, structured parsing artifacts, and every version. Verification lists the prefix again and succeeds only when it is empty. No broader user or bucket prefix is accepted by the deletion service.

## Deletion Service and Failure Semantics

A dedicated `DocumentDeletionService` coordinates the operation:

1. call `begin_delete` and commit logical revocation;
2. delete all matching Qdrant points;
3. delete all matching MinIO objects;
4. verify both stores and confirm that no live catalog or reservation row remains;
5. return a completed result.

The operation is idempotent. A retry starts from the existing same-owner tombstone and executes all cleanup and verification steps again.

If external cleanup raises an error or verification finds a residual object or point, the endpoint returns a `503` response with `status = "purge_pending"` and `tombstoned = true`. This does not reactivate the document. The UI removes it from usable documents immediately and offers a retry action using the retained document ID in local state. A successful retry returns `200` with `status = "deleted"`. An already fully deleted document owned by the same user also returns `200`.

Unknown document IDs and IDs owned by another user return the same `404` response to avoid ownership disclosure.

## API

Add:

```http
DELETE /rag/documents/{document_id}
```

Successful response:

```json
{
  "document_id": "...",
  "status": "deleted",
  "tombstoned": true,
  "objects_remaining": false,
  "vectors_remaining": false
}
```

Partial-cleanup response uses the same safe public shape with `status = "purge_pending"`. Internal exception details remain in server logs and are not exposed to the browser.

The Next.js route `apps/web/app/api/documents/[id]/route.ts` proxies both `GET` and `DELETE` while preserving the upstream status and authenticated session behavior.

## Frontend Interaction

The documents table adds a destructive `删除` action next to `查看`. The detail view also exposes the same action.

- A confirmation dialog names the document and states that deletion is irreversible.
- Only the selected row enters a loading state.
- Confirming once disables repeated clicks until the request settles.
- On `deleted`, the document is removed from the list, current conversation selection, and open detail view.
- On `purge_pending`, it is still removed from all usable UI state and a notice explains that the document is disabled but storage cleanup needs retry. The notice provides a retry button for that document ID.
- On an authorization or validation failure before tombstoning, the document stays visible and an error is shown.

Chat messages with `has_deleted_citations = true` display `原资料已删除，相关引用已移除。` Existing live citations on the same answer continue to render normally.

## Authorization and Safety

- Every catalog, citation, Qdrant, and MinIO operation is scoped by the authenticated `owner_id` and exact `document_id`.
- The endpoint never accepts an arbitrary object-storage prefix from the client.
- Another user's document cannot be discovered or deleted by guessing an ID.
- A tombstoned document ID cannot be uploaded, rebuilt, finalized, or attached to a conversation again.
- The tombstone is retained permanently so stale jobs or restored index data cannot resurrect deleted content.

## Testing Strategy

Development proceeds in test-first slices.

### Catalog tests

- owner can tombstone and revoke a live document;
- another owner receives `404` and no state changes;
- retry through the same-owner tombstone is accepted;
- citations for only the deleted document are removed while answer text and other citations remain;
- affected messages set `has_deleted_citations`;
- reservations and conversation associations are removed;
- reserve, finalize, upsert, list, get, and ready scopes reject tombstoned IDs.

### Storage tests

- Qdrant deletion covers every version for only the requested owner and document;
- MinIO deletion covers every object under the exact document prefix;
- both deletion methods are safe when no matching data remains;
- verification detects intentionally retained test data.

### Service and endpoint tests

- successful deletion returns `deleted` only after verification;
- Qdrant or MinIO failure returns `purge_pending` after logical revocation;
- retry completes cleanup;
- stale candidates are filtered after a concurrent tombstone;
- final citations are revoked when deletion races with answer generation;
- missing and cross-owner IDs have indistinguishable `404` responses.

### Frontend tests

- delete requires confirmation and displays the document name;
- only one row shows deletion progress;
- successful and pending-purge results both remove the document from usable state;
- pending purge exposes retry;
- deleted-citation notices render while remaining live citations still work.

## Acceptance Criteria

1. A confirmed deletion immediately removes the document from lists, detail access, filters, retrieval, and new citations.
2. All Qdrant points for every document version are removed and verified absent.
3. Every MinIO object under the document's exact prefix is removed and verified absent.
4. PostgreSQL retains only the minimal tombstone; document metadata, reservations, conversation links, and citation payloads are removed.
5. Historical question and answer text remains, with a visible deleted-source notice.
6. Partial external failure never makes the document usable and can be resolved by repeating the delete operation.
7. In-flight indexing and querying cannot republish or cite a tombstoned document.
8. Cross-owner deletion is impossible and does not disclose document existence.

## Deferred Work

- bulk deletion;
- scheduled background purge retries beyond the explicit UI retry action;
- tombstone expiry, because permanent retention is required to prevent resurrection;
- deletion audit events outside the minimal tombstone itself.
