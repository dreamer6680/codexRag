CREATE TABLE IF NOT EXISTS rag_document_tombstones (
    document_id text PRIMARY KEY,
    owner_id uuid NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
    deleted_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS rag_document_tombstones_owner_idx
    ON rag_document_tombstones (owner_id, deleted_at DESC);

ALTER TABLE chat_messages
    ADD COLUMN IF NOT EXISTS has_deleted_citations boolean NOT NULL DEFAULT false;
