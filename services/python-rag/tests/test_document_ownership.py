from uuid import UUID

from app.document_catalog import DocumentCatalog


OWNER = UUID("11111111-1111-1111-1111-111111111111")


class FakeResult:
    def __init__(self, rows):
        self.rows = rows

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.rows[0] if self.rows else None


class FakeConnection:
    def __init__(self):
        self.calls = []

    def execute(self, sql, params=None):
        self.calls.append((" ".join(sql.split()), params))
        return FakeResult([])

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


def test_list_documents_always_filters_by_owner(monkeypatch):
    connection = FakeConnection()
    catalog = DocumentCatalog()
    monkeypatch.setattr(catalog, "ensure_schema", lambda: None)
    monkeypatch.setattr(catalog, "_connect", lambda: connection)

    assert catalog.list_documents(OWNER) == []

    sql, params = connection.calls[-1]
    assert "WHERE owner_id = %s" in sql
    assert params == (OWNER,)


def test_get_document_requires_matching_owner(monkeypatch):
    connection = FakeConnection()
    catalog = DocumentCatalog()
    monkeypatch.setattr(catalog, "ensure_schema", lambda: None)
    monkeypatch.setattr(catalog, "_connect", lambda: connection)

    assert catalog.get("doc-1", OWNER) is None

    sql, params = connection.calls[-1]
    assert "document_id = %s AND owner_id = %s" in sql
    assert params == ("doc-1", OWNER)
