from fastapi.testclient import TestClient

from app.main import app
from app.models import QueryResponse


class ActiveCatalog:
    def ready_document_ids(self):
        return ["active-doc"]


def test_query_defaults_to_active_catalog_documents(monkeypatch):
    captured = {}

    async def fake_run_query(question, document_ids, strategy):
        captured["document_ids"] = document_ids
        return QueryResponse(status="refused", answer="no evidence", reason="insufficient_evidence")

    monkeypatch.setattr("app.main.document_catalog", ActiveCatalog())
    monkeypatch.setattr("app.main.run_query", fake_run_query)

    response = TestClient(app).post("/rag/query", json={"question": "question"})

    assert response.status_code == 200
    assert captured["document_ids"] == ["active-doc"]


def test_query_excludes_requested_documents_that_are_not_active(monkeypatch):
    captured = {}

    async def fake_run_query(question, document_ids, strategy):
        captured["document_ids"] = document_ids
        return QueryResponse(status="refused", answer="no evidence", reason="insufficient_evidence")

    monkeypatch.setattr("app.main.document_catalog", ActiveCatalog())
    monkeypatch.setattr("app.main.run_query", fake_run_query)

    response = TestClient(app).post(
        "/rag/query",
        json={"question": "question", "document_ids": ["active-doc", "orphan-doc"]},
    )

    assert response.status_code == 200
    assert captured["document_ids"] == ["active-doc"]
