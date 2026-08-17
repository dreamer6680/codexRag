"""Postgres document catalog for parsed artifact metadata."""
from psycopg.rows import dict_row

from .models import DocumentRecord
from .settings import settings


class DocumentCatalog:
    def _connect(self):
        import psycopg

        return psycopg.connect(settings.postgres_dsn, row_factory=dict_row)

    def ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
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
                )
                """
            )

    def upsert(self, record: DocumentRecord) -> None:
        self.ensure_schema()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO rag_documents (
                    document_id, document_name, version, content_type, parser, status,
                    page_count, pdf_type, chunk_count, original_object_key, markdown_object_key
                )
                VALUES (
                    %(document_id)s, %(document_name)s, %(version)s, %(content_type)s, %(parser)s,
                    %(status)s, %(page_count)s, %(pdf_type)s, %(chunk_count)s,
                    %(original_object_key)s, %(markdown_object_key)s
                )
                ON CONFLICT (document_id) DO UPDATE SET
                    document_name = EXCLUDED.document_name,
                    version = EXCLUDED.version,
                    content_type = EXCLUDED.content_type,
                    parser = EXCLUDED.parser,
                    status = EXCLUDED.status,
                    page_count = EXCLUDED.page_count,
                    pdf_type = EXCLUDED.pdf_type,
                    chunk_count = EXCLUDED.chunk_count,
                    original_object_key = EXCLUDED.original_object_key,
                    markdown_object_key = EXCLUDED.markdown_object_key,
                    updated_at = now()
                """,
                record.model_dump(exclude={"created_at", "updated_at"}),
            )

    def list_documents(self) -> list[DocumentRecord]:
        self.ensure_schema()
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT document_id, document_name, version, content_type, parser, status,
                       page_count, pdf_type, chunk_count, original_object_key, markdown_object_key,
                       created_at::text, updated_at::text
                FROM rag_documents
                ORDER BY updated_at DESC
                """
            ).fetchall()
        return [DocumentRecord(**row) for row in rows]

    def ready_document_ids(self) -> list[str]:
        self.ensure_schema()
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT document_id
                FROM rag_documents
                WHERE status = 'ready'
                ORDER BY updated_at DESC
                """
            ).fetchall()
        return [row["document_id"] for row in rows]

    def get(self, document_id: str) -> DocumentRecord | None:
        self.ensure_schema()
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT document_id, document_name, version, content_type, parser, status,
                       page_count, pdf_type, chunk_count, original_object_key, markdown_object_key,
                       created_at::text, updated_at::text
                FROM rag_documents
                WHERE document_id = %s
                """,
                (document_id,),
            ).fetchone()
        return DocumentRecord(**row) if row else None
