"""Owner-scoped persistence for conversations and messages."""

import json
from pathlib import Path
from uuid import UUID, uuid4

from .auth import AuthenticatedUser
from .models import (
    ChatMessage,
    Citation,
    ConversationDetail,
    ConversationSummary,
)
from .settings import settings


def default_title(question: str) -> str:
    normalized = " ".join(question.split())
    return normalized[:36] if normalized else "新聊天"


class ChatCatalog:
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
                """INSERT INTO app_users (id, email, display_name) VALUES (%s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET email = EXCLUDED.email,
                display_name = COALESCE(EXCLUDED.display_name, app_users.display_name), updated_at = now()""",
                (user.id, user.email, user.display_name),
            )

    def create_conversation(self, owner_id: UUID, title: str | None = None) -> ConversationSummary:
        self.ensure_schema()
        conversation_id = uuid4()
        with self._connect() as conn:
            row = conn.execute(
                """INSERT INTO chat_conversations (id, owner_id, title) VALUES (%s, %s, %s)
                RETURNING id, title, created_at, updated_at""",
                (conversation_id, owner_id, (title or "新聊天").strip() or "新聊天"),
            ).fetchone()
        return ConversationSummary(**row)

    def list_conversations(self, owner_id: UUID) -> list[ConversationSummary]:
        self.ensure_schema()
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT id, title, created_at, updated_at FROM chat_conversations
                WHERE owner_id = %s ORDER BY updated_at DESC""",
                (owner_id,),
            ).fetchall()
        return [ConversationSummary(**row) for row in rows]

    def get_conversation(self, conversation_id: UUID, owner_id: UUID) -> ConversationDetail | None:
        self.ensure_schema()
        with self._connect() as conn:
            row = conn.execute(
                """SELECT id, title, summary, summarized_through_message_id, created_at, updated_at FROM chat_conversations
                WHERE id = %s AND owner_id = %s""",
                (conversation_id, owner_id),
            ).fetchone()
            if not row:
                return None
            message_rows = conn.execute(
                """SELECT id, conversation_id, role, content, status, citations, confidence, error, created_at
                FROM chat_messages WHERE conversation_id = %s AND owner_id = %s ORDER BY created_at""",
                (conversation_id, owner_id),
            ).fetchall()
            document_rows = conn.execute(
                """SELECT document_id FROM conversation_documents
                WHERE conversation_id = %s AND owner_id = %s ORDER BY document_id""",
                (conversation_id, owner_id),
            ).fetchall()
        messages = [ChatMessage(**message) for message in message_rows]
        return ConversationDetail(
            **row,
            messages=messages,
            selected_document_ids=[item["document_id"] for item in document_rows],
        )

    def update_conversation(
        self,
        conversation_id: UUID,
        owner_id: UUID,
        title: str | None = None,
        document_ids: list[str] | None = None,
    ) -> ConversationDetail | None:
        self.ensure_schema()
        with self._connect() as conn:
            exists = conn.execute(
                "SELECT 1 FROM chat_conversations WHERE id = %s AND owner_id = %s",
                (conversation_id, owner_id),
            ).fetchone()
            if not exists:
                return None
            if title is not None:
                conn.execute(
                    "UPDATE chat_conversations SET title = %s, updated_at = now() WHERE id = %s AND owner_id = %s",
                    (title.strip(), conversation_id, owner_id),
                )
            if document_ids is not None:
                unique_ids = list(dict.fromkeys(document_ids))
                if unique_ids:
                    owned = conn.execute(
                        "SELECT document_id FROM rag_documents WHERE owner_id = %s AND document_id = ANY(%s)",
                        (owner_id, unique_ids),
                    ).fetchall()
                    if {row["document_id"] for row in owned} != set(unique_ids):
                        raise ValueError("包含无权访问的文档")
                conn.execute(
                    "DELETE FROM conversation_documents WHERE conversation_id = %s AND owner_id = %s",
                    (conversation_id, owner_id),
                )
                for document_id in unique_ids:
                    conn.execute(
                        """INSERT INTO conversation_documents (conversation_id, document_id, owner_id)
                        VALUES (%s, %s, %s)""",
                        (conversation_id, document_id, owner_id),
                    )
        return self.get_conversation(conversation_id, owner_id)

    def start_turn(self, conversation_id: UUID, owner_id: UUID, question: str) -> tuple[ConversationSummary, ChatMessage, ChatMessage] | None:
        self.ensure_schema()
        user_message_id, assistant_message_id = uuid4(), uuid4()
        with self._connect() as conn:
            conversation = conn.execute(
                "SELECT id, title, created_at, updated_at FROM chat_conversations WHERE id = %s AND owner_id = %s",
                (conversation_id, owner_id),
            ).fetchone()
            if not conversation:
                return None
            if conversation["title"] == "新聊天":
                conversation = conn.execute(
                    """UPDATE chat_conversations SET title = %s, updated_at = now()
                    WHERE id = %s AND owner_id = %s RETURNING id, title, created_at, updated_at""",
                    (default_title(question), conversation_id, owner_id),
                ).fetchone()
            user_row = conn.execute(
                """INSERT INTO chat_messages (id, conversation_id, owner_id, role, content, status)
                VALUES (%s, %s, %s, 'user', %s, 'completed')
                RETURNING id, conversation_id, role, content, status, citations, confidence, error, created_at""",
                (user_message_id, conversation_id, owner_id, question),
            ).fetchone()
            assistant_row = conn.execute(
                """INSERT INTO chat_messages (id, conversation_id, owner_id, role, content, status)
                VALUES (%s, %s, %s, 'assistant', '', 'pending')
                RETURNING id, conversation_id, role, content, status, citations, confidence, error, created_at""",
                (assistant_message_id, conversation_id, owner_id),
            ).fetchone()
            conversation = conn.execute(
                """UPDATE chat_conversations SET updated_at = now() WHERE id = %s AND owner_id = %s
                RETURNING id, title, created_at, updated_at""",
                (conversation_id, owner_id),
            ).fetchone()
        return ConversationSummary(**conversation), ChatMessage(**user_row), ChatMessage(**assistant_row)

    def finish_turn(
        self,
        assistant_id: UUID,
        owner_id: UUID,
        content: str,
        citations: list[Citation],
        confidence: str = "none",
    ) -> ChatMessage:
        with self._connect() as conn:
            row = conn.execute(
                """UPDATE chat_messages SET content = %s, citations = %s::jsonb, confidence = %s,
                status = 'completed', error = NULL
                WHERE id = %s AND owner_id = %s
                RETURNING id, conversation_id, role, content, status, citations, confidence, error, created_at""",
                (content, json.dumps([item.model_dump() for item in citations]), confidence, assistant_id, owner_id),
            ).fetchone()
        return ChatMessage(**row)

    def fail_turn(self, assistant_id: UUID, owner_id: UUID, error: str) -> ChatMessage:
        with self._connect() as conn:
            row = conn.execute(
                """UPDATE chat_messages SET status = 'failed', error = %s WHERE id = %s AND owner_id = %s
                RETURNING id, conversation_id, role, content, status, citations, confidence, error, created_at""",
                (error, assistant_id, owner_id),
            ).fetchone()
        return ChatMessage(**row)

    def update_summary(self, conversation_id: UUID, owner_id: UUID, summary: str, through_message_id: UUID) -> None:
        with self._connect() as conn:
            conn.execute(
                """UPDATE chat_conversations SET summary = %s, summarized_through_message_id = %s
                WHERE id = %s AND owner_id = %s""",
                (summary[:1000], through_message_id, conversation_id, owner_id),
            )
