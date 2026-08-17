"""Owner-scoped Postgres document catalog for parsed artifact metadata."""
from pathlib import Path
from uuid import UUID

from .auth import AuthenticatedUser
from .models import DocumentRecord
from .settings import settings


class DocumentCatalog:
    def _connect(self):
        import psycopg
        from psycopg.rows import dict_row

        return psycopg.connect(settings.postgres_dsn, row_factory=dict_row)

    def ensure_schema(self) -> None:
        migration = Path(__file__).resolve().parents[1] / "migrations" / "001_user_chat.sql"
        with self._connect() as conn:
            conn.execute(migration.read_text(encoding="utf-8"))

    def upsert_user(self, user: AuthenticatedUser) -> None:
        self.ensure_schema()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO app_users (id, email, display_name)
                VALUES (%s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    email = EXCLUDED.email,
                    display_name = COALESCE(EXCLUDED.display_name, app_users.display_name),
                    updated_at = now()
                """,
                (user.id, user.email, user.display_name),
            )

    def upsert(self, record: DocumentRecord, owner_id: UUID) -> None:
        self.ensure_schema()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO rag_documents (
                    owner_id, document_id, document_name, version, content_type, parser, status,
                    page_count, pdf_type, chunk_count, original_object_key, markdown_object_key
                )
                VALUES (
                    %(owner_id)s, %(document_id)s, %(document_name)s, %(version)s, %(content_type)s, %(parser)s,
                    %(status)s, %(page_count)s, %(pdf_type)s, %(chunk_count)s,
                    %(original_object_key)s, %(markdown_object_key)s
                )
                ON CONFLICT (document_id) DO UPDATE SET
                    owner_id = EXCLUDED.owner_id,
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
                WHERE rag_documents.owner_id = EXCLUDED.owner_id
                """,
                {**record.model_dump(exclude={"created_at", "updated_at"}), "owner_id": owner_id},
            )

    def list_documents(self, owner_id: UUID) -> list[DocumentRecord]:
        self.ensure_schema()
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT owner_id, document_id, document_name, version, content_type, parser, status,
                       page_count, pdf_type, chunk_count, original_object_key, markdown_object_key,
                       created_at::text, updated_at::text
                FROM rag_documents
                WHERE owner_id = %s
                ORDER BY updated_at DESC
                """,
                (owner_id,),
            ).fetchall()
        return [DocumentRecord(**row) for row in rows]

    def get(self, document_id: str, owner_id: UUID) -> DocumentRecord | None:
        self.ensure_schema()
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT owner_id, document_id, document_name, version, content_type, parser, status,
                       page_count, pdf_type, chunk_count, original_object_key, markdown_object_key,
                       created_at::text, updated_at::text
                FROM rag_documents
                WHERE document_id = %s AND owner_id = %s
                """,
                (document_id, owner_id),
            ).fetchone()
        return DocumentRecord(**row) if row else None
