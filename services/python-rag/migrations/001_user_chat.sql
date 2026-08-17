CREATE TABLE IF NOT EXISTS app_users (
    id uuid PRIMARY KEY,
    email text,
    display_name text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS rag_documents (
    document_id text PRIMARY KEY,
    document_name text NOT NULL,
    version integer NOT NULL,
    content_type text,
    parser text NOT NULL,
    status text NOT NULL,
    page_count integer,
    pdf_type text,
    chunk_count integer NOT NULL,
    original_object_key text NOT NULL,
    markdown_object_key text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE rag_documents
    ADD COLUMN IF NOT EXISTS owner_id uuid REFERENCES app_users(id);

CREATE INDEX IF NOT EXISTS rag_documents_owner_updated_idx
    ON rag_documents (owner_id, updated_at DESC);

CREATE OR REPLACE FUNCTION require_rag_document_owner()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.owner_id IS NULL THEN
        RAISE EXCEPTION 'owner_id is required for new document writes';
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS rag_documents_require_owner ON rag_documents;
CREATE TRIGGER rag_documents_require_owner
BEFORE INSERT OR UPDATE ON rag_documents
FOR EACH ROW EXECUTE FUNCTION require_rag_document_owner();

CREATE TABLE IF NOT EXISTS chat_conversations (
    id uuid PRIMARY KEY,
    owner_id uuid NOT NULL REFERENCES app_users(id),
    title text NOT NULL DEFAULT '新聊天',
    summary text NOT NULL DEFAULT '',
    summarized_through_message_id uuid,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS chat_conversations_owner_updated_idx
    ON chat_conversations (owner_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS chat_messages (
    id uuid PRIMARY KEY,
    conversation_id uuid NOT NULL REFERENCES chat_conversations(id) ON DELETE CASCADE,
    owner_id uuid NOT NULL REFERENCES app_users(id),
    role text NOT NULL CHECK (role IN ('user', 'assistant')),
    content text NOT NULL DEFAULT '',
    status text NOT NULL CHECK (status IN ('pending', 'completed', 'failed')),
    citations jsonb NOT NULL DEFAULT '[]'::jsonb,
    error text,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS chat_messages_conversation_created_idx
    ON chat_messages (owner_id, conversation_id, created_at);

CREATE TABLE IF NOT EXISTS conversation_documents (
    conversation_id uuid NOT NULL REFERENCES chat_conversations(id) ON DELETE CASCADE,
    document_id text NOT NULL REFERENCES rag_documents(document_id) ON DELETE CASCADE,
    owner_id uuid NOT NULL REFERENCES app_users(id),
    PRIMARY KEY (conversation_id, document_id)
);

CREATE INDEX IF NOT EXISTS conversation_documents_owner_idx
    ON conversation_documents (owner_id, conversation_id);
