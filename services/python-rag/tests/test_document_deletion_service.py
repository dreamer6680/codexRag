from uuid import uuid4

import pytest

from app.document_deletion import (
    DocumentDeletionService,
    DocumentNotFound,
    DocumentPurgePending,
)


OWNER = uuid4()


class Catalog:
    def __init__(self, accepted=True, events=None):
        self.accepted = accepted
        self.events = events if events is not None else []

    def begin_delete(self, owner_id, document_id):
        self.events.append("tombstone")
        return self.accepted


class Store:
    def __init__(self, label, events, remaining=False, error=None):
        self.label = label
        self.events = events
        self.remaining = remaining
        self.error = error

    def delete_document(self, owner_id, document_id):
        self.events.append(f"{self.label}-delete")
        if self.error:
            raise self.error

    def document_exists(self, owner_id, document_id):
        self.events.append(f"{self.label}-check")
        return self.remaining


def service(events, *, accepted=True, vector_remaining=False, object_remaining=False, object_error=None):
    return DocumentDeletionService(
        catalog=Catalog(accepted, events),
        vectors=Store("vectors", events, vector_remaining),
        objects=Store("objects", events, object_remaining, object_error),
    )


def test_delete_revokes_before_external_purge_and_verification():
    events = []

    result = service(events).delete(OWNER, "doc-1")

    assert events == [
        "tombstone",
        "vectors-delete",
        "objects-delete",
        "vectors-check",
        "objects-check",
    ]
    assert result.status == "deleted"
    assert result.tombstoned is True


def test_delete_reports_pending_after_logical_revocation_when_object_purge_fails():
    events = []

    with pytest.raises(DocumentPurgePending) as raised:
        service(events, object_error=RuntimeError("offline")).delete(OWNER, "doc-1")

    assert raised.value.result.status == "purge_pending"
    assert raised.value.result.tombstoned is True
    assert raised.value.result.objects_remaining is True


def test_delete_hides_unknown_or_cross_owner_document():
    with pytest.raises(DocumentNotFound):
        service([], accepted=False).delete(OWNER, "doc-1")
