"""Owner-scoped Postgres document catalog for parsed artifact metadata."""
from uuid import UUID

from .auth import AuthenticatedUser
from .database import run_migrations
from .models import DocumentRecord
from .settings import settings


class DocumentCatalog:
    def _connect(self):
        import psycopg
        from psycopg.rows import dict_row

        return psycopg.connect(settings.postgres_dsn, row_factory=dict_row)

    def ensure_schema(self) -> None:
        run_migrations(self._connect)

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
                SELECT
                    %(owner_id)s, %(document_id)s, %(document_name)s, %(version)s, %(content_type)s, %(parser)s,
                    %(status)s, %(page_count)s, %(pdf_type)s, %(chunk_count)s,
                    %(original_object_key)s, %(markdown_object_key)s
                WHERE NOT EXISTS (
                    SELECT 1 FROM rag_document_tombstones
                    WHERE document_id = %(document_id)s
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

    def reserve_index_version(
        self,
        owner_id: UUID,
        document_id: str,
        document_name: str,
        version: int,
    ) -> bool:
        """Reserve a new version without withdrawing the owner's ready version."""
        self.ensure_schema()
        with self._connect() as conn:
            row = conn.execute(
                """
                INSERT INTO rag_document_index_reservations (document_id, owner_id, version, status)
                SELECT %(document_id)s, %(owner_id)s, %(version)s, 'indexing'
                WHERE NOT EXISTS (
                    SELECT 1 FROM rag_documents
                    WHERE document_id = %(document_id)s AND owner_id <> %(owner_id)s
                )
                  AND NOT EXISTS (
                    SELECT 1 FROM rag_document_tombstones
                    WHERE document_id = %(document_id)s
                  )
                  AND %(version)s > COALESCE(
                    (SELECT version FROM rag_documents
                     WHERE document_id = %(document_id)s AND owner_id = %(owner_id)s), 0
                  )
                ON CONFLICT (document_id) DO UPDATE SET
                    owner_id = EXCLUDED.owner_id,
                    version = EXCLUDED.version,
                    status = 'indexing',
                    updated_at = now()
                WHERE rag_document_index_reservations.owner_id = EXCLUDED.owner_id
                  AND rag_document_index_reservations.version < EXCLUDED.version
                  AND EXCLUDED.version > COALESCE(
                    (SELECT version FROM rag_documents
                     WHERE document_id = EXCLUDED.document_id
                       AND owner_id = EXCLUDED.owner_id), 0
                  )
                RETURNING document_id
                """,
                {"document_id": document_id, "owner_id": owner_id, "version": version},
            ).fetchone()
        return row is not None

    def finalize_index(self, record: DocumentRecord, owner_id: UUID) -> bool:
        """Atomically publish an index result if this owner still holds the reservation."""
        self.ensure_schema()
        values = {
            **record.model_dump(exclude={"created_at", "updated_at"}),
            "owner_id": owner_id,
        }
        with self._connect() as conn:
            reservation = conn.execute(
                """
                SELECT document_id
                FROM rag_document_index_reservations
                WHERE document_id = %s AND owner_id = %s
                  AND version = %s AND status = 'indexing'
                FOR UPDATE
                """,
                (record.document_id, owner_id, record.version),
            ).fetchone()
            if reservation is None:
                return False
            published = conn.execute(
                """
                INSERT INTO rag_documents (
                    owner_id, document_id, document_name, version, content_type, parser, status,
                    page_count, pdf_type, chunk_count, original_object_key, markdown_object_key
                ) SELECT
                    %(owner_id)s, %(document_id)s, %(document_name)s, %(version)s,
                    %(content_type)s, %(parser)s, 'ready', %(page_count)s, %(pdf_type)s,
                    %(chunk_count)s, %(original_object_key)s, %(markdown_object_key)s
                WHERE NOT EXISTS (
                    SELECT 1 FROM rag_document_tombstones
                    WHERE document_id = %(document_id)s
                )
                ON CONFLICT (document_id) DO UPDATE SET
                    document_name = EXCLUDED.document_name,
                    version = EXCLUDED.version,
                    content_type = EXCLUDED.content_type,
                    parser = EXCLUDED.parser,
                    status = 'ready',
                    page_count = EXCLUDED.page_count,
                    pdf_type = EXCLUDED.pdf_type,
                    chunk_count = EXCLUDED.chunk_count,
                    original_object_key = EXCLUDED.original_object_key,
                    markdown_object_key = EXCLUDED.markdown_object_key,
                    updated_at = now()
                WHERE rag_documents.owner_id = EXCLUDED.owner_id
                  AND rag_documents.version < EXCLUDED.version
                RETURNING document_id
                """,
                values,
            ).fetchone()
            if published is None:
                return False
            conn.execute(
                """
                UPDATE rag_document_index_reservations
                SET status = 'ready', updated_at = now()
                WHERE document_id = %s AND owner_id = %s AND version = %s
                """,
                (record.document_id, owner_id, record.version),
            )
        return True

    def mark_index_failed(self, owner_id: UUID, document_id: str, version: int) -> None:
        self.ensure_schema()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE rag_document_index_reservations
                SET status = 'index_failed', updated_at = now()
                WHERE document_id = %s AND owner_id = %s
                  AND version = %s AND status = 'indexing'
                """,
                (document_id, owner_id, version),
            )

    def ready_document_scopes(
        self,
        owner_id: UUID,
        document_ids: list[str] | None = None,
    ) -> list[tuple[str, int]]:
        self.ensure_schema()
        params: list[object] = [owner_id]
        selected = ""
        if document_ids:
            selected = " AND document_id = ANY(%s)"
            params.append(document_ids)
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT document_id, version
                FROM rag_documents d
                WHERE owner_id = %s AND status = 'ready'{selected}
                  AND NOT EXISTS (
                    SELECT 1 FROM rag_document_tombstones t
                    WHERE t.document_id = d.document_id
                  )
                ORDER BY updated_at DESC
                """,
                params,
            ).fetchall()
        return [(row["document_id"], row["version"]) for row in rows]

    def list_documents(self, owner_id: UUID) -> list[DocumentRecord]:
        self.ensure_schema()
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT owner_id, document_id, document_name, version, content_type, parser, status,
                       page_count, pdf_type, chunk_count, original_object_key, markdown_object_key,
                       created_at::text, updated_at::text
                FROM rag_documents d
                WHERE owner_id = %s
                  AND NOT EXISTS (
                    SELECT 1 FROM rag_document_tombstones t
                    WHERE t.document_id = d.document_id
                  )
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
                FROM rag_documents d
                WHERE document_id = %s AND owner_id = %s
                  AND NOT EXISTS (
                    SELECT 1 FROM rag_document_tombstones t
                    WHERE t.document_id = d.document_id
                  )
                """,
                (document_id, owner_id),
            ).fetchone()
        return DocumentRecord(**row) if row else None

    def begin_delete(self, owner_id: UUID, document_id: str) -> bool:
        """Atomically revoke a document before external storage is purged."""
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
            conn.execute(
                """UPDATE chat_messages AS message
                SET citations = COALESCE((
                    SELECT jsonb_agg(citation)
                    FROM jsonb_array_elements(message.citations) AS citation
                    WHERE citation->>'document_id' <> %s
                ), '[]'::jsonb),
                has_deleted_citations = true
                WHERE message.owner_id = %s
                  AND EXISTS (
                    SELECT 1 FROM jsonb_array_elements(message.citations) AS citation
                    WHERE citation->>'document_id' = %s
                  )""",
                (document_id, owner_id, document_id),
            )
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

    def live_document_ids(self, owner_id: UUID, document_ids: list[str]) -> set[str]:
        """Return the subset still ready and not tombstoned."""
        if not document_ids:
            return set()
        self.ensure_schema()
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT d.document_id
                FROM rag_documents d
                WHERE d.owner_id = %s AND d.status = 'ready'
                  AND d.document_id = ANY(%s)
                  AND NOT EXISTS (
                    SELECT 1 FROM rag_document_tombstones t
                    WHERE t.document_id = d.document_id
                  )""",
                (owner_id, document_ids),
            ).fetchall()
        return {row["document_id"] for row in rows}
