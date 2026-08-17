from fastapi.testclient import TestClient

from app.main import app
from app.models import QueryResponse


class ActiveCatalog:
    def ready_document_scopes(self):
        return [("active-doc", 2)]


def test_query_defaults_to_active_catalog_documents(monkeypatch):
    captured = {}

    async def fake_run_query(question, document_scope, strategy):
        captured["document_scope"] = document_scope
        return QueryResponse(status="refused", answer="no evidence", reason="insufficient_evidence")

    monkeypatch.setattr("app.main.document_catalog", ActiveCatalog())
    monkeypatch.setattr("app.main.run_query", fake_run_query)

    response = TestClient(app).post("/rag/query", json={"question": "question"})

    assert response.status_code == 200
    assert captured["document_scope"] == [("active-doc", 2)]


def test_query_excludes_requested_documents_that_are_not_active(monkeypatch):
    captured = {}

    async def fake_run_query(question, document_scope, strategy):
        captured["document_scope"] = document_scope
        return QueryResponse(status="refused", answer="no evidence", reason="insufficient_evidence")

    monkeypatch.setattr("app.main.document_catalog", ActiveCatalog())
    monkeypatch.setattr("app.main.run_query", fake_run_query)

    response = TestClient(app).post(
        "/rag/query",
        json={"question": "question", "document_ids": ["active-doc", "orphan-doc"]},
    )

    assert response.status_code == 200
    assert captured["document_scope"] == [("active-doc", 2)]


def test_query_fails_closed_when_catalog_is_unavailable(monkeypatch):
    class BrokenCatalog:
        def ready_document_scopes(self):
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
