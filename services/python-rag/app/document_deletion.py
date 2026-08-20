"""Tombstone-first, retry-safe document deletion orchestration."""
from uuid import UUID

from .document_catalog import DocumentCatalog
from .models import DocumentDeleteResponse
from .object_storage import ObjectStorage
from .vector_store import VectorStore


class DocumentNotFound(LookupError):
    pass


class DocumentPurgePending(RuntimeError):
    def __init__(self, result: DocumentDeleteResponse):
        self.result = result
        super().__init__("document purge pending")


class DocumentDeletionService:
    def __init__(
        self,
        catalog: DocumentCatalog | None = None,
        vectors: VectorStore | None = None,
        objects: ObjectStorage | None = None,
    ) -> None:
        self.catalog = catalog or DocumentCatalog()
        self.vectors = vectors or VectorStore()
        self.objects = objects or ObjectStorage()

    def delete(self, owner_id: UUID, document_id: str) -> DocumentDeleteResponse:
        if not self.catalog.begin_delete(owner_id, document_id):
            raise DocumentNotFound(document_id)

        vector_failed = False
        object_failed = False
        try:
            self.vectors.delete_document(owner_id, document_id)
        except Exception:
            vector_failed = True
        try:
            self.objects.delete_document(owner_id, document_id)
        except Exception:
            object_failed = True

        vectors_remaining = vector_failed or self._exists(self.vectors, owner_id, document_id)
        objects_remaining = object_failed or self._exists(self.objects, owner_id, document_id)
        result = DocumentDeleteResponse(
            document_id=document_id,
            status="purge_pending" if vectors_remaining or objects_remaining else "deleted",
            tombstoned=True,
            objects_remaining=objects_remaining,
            vectors_remaining=vectors_remaining,
        )
        if result.status == "purge_pending":
            raise DocumentPurgePending(result)
        return result

    @staticmethod
    def _exists(store, owner_id: UUID, document_id: str) -> bool:
        try:
            return store.document_exists(owner_id, document_id)
        except Exception:
            return True
