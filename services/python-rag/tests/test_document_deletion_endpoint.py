from uuid import UUID

from fastapi.testclient import TestClient

from app.auth import AuthenticatedUser, require_user
from app.document_deletion import DocumentNotFound, DocumentPurgePending
from app.main import app
from app.models import DocumentDeleteResponse


USER = AuthenticatedUser(
    id=UUID("11111111-1111-1111-1111-111111111111"),
    email="owner@example.com",
)


class Deletion:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.called = None

    def delete(self, owner_id, document_id):
        self.called = (owner_id, document_id)
        if self.error:
            raise self.error
        return self.result


def request(monkeypatch, deletion):
    monkeypatch.setattr("app.main.document_deletion", deletion)
    app.dependency_overrides[require_user] = lambda: USER
    return TestClient(app).delete("/rag/documents/doc-1")


def test_delete_endpoint_returns_verified_success(monkeypatch):
    deletion = Deletion(DocumentDeleteResponse(
        document_id="doc-1",
        status="deleted",
        objects_remaining=False,
        vectors_remaining=False,
    ))

    response = request(monkeypatch, deletion)

    assert response.status_code == 200
    assert deletion.called == (USER.id, "doc-1")
    assert response.json()["status"] == "deleted"


def test_delete_endpoint_returns_safe_pending_shape(monkeypatch):
    pending = DocumentDeleteResponse(
        document_id="doc-1",
        status="purge_pending",
        objects_remaining=True,
        vectors_remaining=False,
    )

    response = request(monkeypatch, Deletion(error=DocumentPurgePending(pending)))

    assert response.status_code == 503
    assert response.json() == pending.model_dump()


def test_delete_endpoint_hides_unknown_document(monkeypatch):
    response = request(monkeypatch, Deletion(error=DocumentNotFound("doc-1")))

    assert response.status_code == 404
    assert response.json()["detail"] == "Document not found"
