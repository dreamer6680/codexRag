import pytest
from fastapi.testclient import TestClient
from uuid import UUID

from app.auth import AuthenticatedUser, require_user
from app.main import app
from app.models import QueryResponse

USER = AuthenticatedUser(id=UUID("11111111-1111-1111-1111-111111111111"), email="reader@example.com")


@pytest.fixture(autouse=True)
def authenticated_user():
    app.dependency_overrides[require_user] = lambda: USER
    yield
    app.dependency_overrides.pop(require_user, None)


class ActiveCatalog:
    def __init__(self):
        self.requested = None

    def upsert_user(self, user):
        pass

    def ready_document_scopes(self, owner_id, document_ids=None):
        self.requested = (owner_id, document_ids)
        return [("active-doc", 2)]

    def get(self, document_id, owner_id):
        return object() if document_id == "active-doc" else None


def test_query_defaults_to_active_catalog_documents(monkeypatch):
    captured = {}
    catalog = ActiveCatalog()

    async def fake_run_query(question, owner_id, document_ids, strategy):
        captured["document_ids"] = document_ids
        return QueryResponse(status="refused", answer="no evidence", reason="insufficient_evidence")

    monkeypatch.setattr("app.main.document_catalog", catalog)
    monkeypatch.setattr("app.main.run_query", fake_run_query)

    response = TestClient(app).post("/rag/query", json={"question": "question"})

    assert response.status_code == 200
    assert catalog.requested == (USER.id, [])
    assert captured["document_ids"] == []


def test_query_excludes_requested_documents_that_are_not_active(monkeypatch):
    captured = {}
    catalog = ActiveCatalog()

    async def fake_run_query(question, owner_id, document_ids, strategy):
        captured["document_ids"] = document_ids
        return QueryResponse(status="refused", answer="no evidence", reason="insufficient_evidence")

    monkeypatch.setattr("app.main.document_catalog", catalog)
    monkeypatch.setattr("app.main.run_query", fake_run_query)

    response = TestClient(app).post(
        "/rag/query",
        json={"question": "question", "document_ids": ["active-doc"]},
    )

    assert response.status_code == 200
    assert catalog.requested == (USER.id, ["active-doc"])
    assert captured["document_ids"] == ["active-doc"]


def test_query_fails_closed_when_catalog_is_unavailable(monkeypatch):
    class BrokenCatalog:
        def upsert_user(self, user):
            pass

        def ready_document_scopes(self, owner_id, document_ids=None):
            raise RuntimeError("postgres offline")

    monkeypatch.setattr("app.main.document_catalog", BrokenCatalog())

    response = TestClient(app).post("/rag/query", json={"question": "question"})

    assert response.status_code == 200
    assert response.json() == {
        "status": "unavailable",
        "answer": "文档目录当前不可用。",
        "citations": [],
        "confidence": "none",
        "model": None,
        "reason": "catalog_unavailable",
    }
