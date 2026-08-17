from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from app.auth import AuthenticatedUser, require_user
from app.main import app
from app.models import (
    ChatMessage,
    Citation,
    ConversationDetail,
    ConversationSummary,
    QueryResponse,
)
from app.retrieval import CatalogUnavailableError


OWNER = UUID("11111111-1111-1111-1111-111111111111")
USER = AuthenticatedUser(id=OWNER, email="reader@example.com")
CONVERSATION_ID = UUID("22222222-2222-2222-2222-222222222222")


def now():
    return datetime.now(timezone.utc)


def summary(title="新聊天"):
    return ConversationSummary(id=CONVERSATION_ID, title=title, created_at=now(), updated_at=now())


def message(role, status, content=""):
    return ChatMessage(
        id=uuid4(),
        conversation_id=CONVERSATION_ID,
        role=role,
        content=content,
        status=status,
        created_at=now(),
    )


class FakeChatCatalog:
    def __init__(self, exists=True):
        self.exists = exists
        self.saved_citations = None
        self.saved_confidence = None
        self.failed_error = None

    def get_conversation(self, conversation_id, owner_id):
        if not self.exists or conversation_id != CONVERSATION_ID or owner_id != OWNER:
            return None
        return ConversationDetail(**summary().model_dump(), summary="", messages=[], selected_document_ids=[])

    def start_turn(self, conversation_id, owner_id, question):
        assert owner_id == OWNER
        assert question == "发布需要哪些材料？"
        return summary("发布需要哪些材料？"), message("user", "completed", question), message("assistant", "pending")

    def finish_turn(self, assistant_id, owner_id, content, citations, confidence="none"):
        assert owner_id == OWNER
        self.saved_citations = citations
        self.saved_confidence = confidence
        return ChatMessage(
            id=assistant_id,
            conversation_id=CONVERSATION_ID,
            role="assistant",
            content=content,
            status="completed",
            citations=citations,
            confidence=confidence,
            created_at=now(),
        )

    def fail_turn(self, assistant_id, owner_id, error):
        self.failed_error = error
        return ChatMessage(
            id=assistant_id,
            conversation_id=CONVERSATION_ID,
            role="assistant",
            content="",
            status="failed",
            error=error,
            created_at=now(),
        )


def test_send_message_persists_answer_and_citation_snapshot(monkeypatch):
    catalog = FakeChatCatalog()
    citation = Citation(
        document_id="doc-1",
        document_name="发布规范.pdf",
        version=1,
        excerpt="发布前提交检查表",
        confidence=0.9,
    )

    async def fake_run_query(*_args, **_kwargs):
        return QueryResponse(status="answered", answer="需要提交检查表。[1]", citations=[citation], confidence="high")

    monkeypatch.setattr("app.main.chat_catalog", catalog)
    monkeypatch.setattr("app.main.run_query", fake_run_query)
    app.dependency_overrides[require_user] = lambda: USER
    try:
        response = TestClient(app).post(
            f"/rag/conversations/{CONVERSATION_ID}/messages",
            json={"question": "发布需要哪些材料？"},
        )
    finally:
        app.dependency_overrides.pop(require_user, None)

    assert response.status_code == 200
    assert response.json()["assistant_message"]["content"] == "需要提交检查表。[1]"
    assert response.json()["assistant_message"]["confidence"] == "high"
    assert catalog.saved_citations == [citation]
    assert catalog.saved_confidence == "high"


def test_catalog_failure_marks_conversation_turn_unavailable(monkeypatch):
    catalog = FakeChatCatalog()

    async def unavailable_retrieval(*_args, **_kwargs):
        raise CatalogUnavailableError("postgres offline")

    monkeypatch.setattr("app.main.chat_catalog", catalog)
    monkeypatch.setattr("app.graph.MultiStrategyRetriever.retrieve", unavailable_retrieval)
    app.dependency_overrides[require_user] = lambda: USER
    try:
        response = TestClient(app).post(
            f"/rag/conversations/{CONVERSATION_ID}/messages",
            json={"question": "发布需要哪些材料？"},
        )
    finally:
        app.dependency_overrides.pop(require_user, None)

    assert response.status_code == 200
    assert response.json()["assistant_message"]["status"] == "failed"
    assert catalog.failed_error == "文档目录当前不可用。"


def test_opening_another_users_conversation_returns_not_found(monkeypatch):
    monkeypatch.setattr("app.main.chat_catalog", FakeChatCatalog(exists=False))
    app.dependency_overrides[require_user] = lambda: USER
    try:
        response = TestClient(app).get(f"/rag/conversations/{CONVERSATION_ID}")
    finally:
        app.dependency_overrides.pop(require_user, None)

    assert response.status_code == 404
