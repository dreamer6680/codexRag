"""MinIO-backed storage for original and parsed document artifacts."""
from io import BytesIO

from .settings import settings


class ObjectStorage:
    def __init__(self) -> None:
        self.bucket = settings.minio_bucket
        self._client = None

    @property
    def client(self):
        if self._client is None:
            from minio import Minio

            self._client = Minio(
                settings.minio_endpoint,
                access_key=settings.minio_access_key,
                secret_key=settings.minio_secret_key,
                secure=settings.minio_secure,
            )
        return self._client

    def ensure_bucket(self) -> None:
        if not self.client.bucket_exists(self.bucket):
            self.client.make_bucket(self.bucket)

    def put_bytes(self, key: str, data: bytes, content_type: str) -> None:
        self.ensure_bucket()
        self.client.put_object(self.bucket, key, BytesIO(data), len(data), content_type=content_type)

    def get_bytes(self, key: str) -> bytes:
        response = self.client.get_object(self.bucket, key)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()

    def stream(self, key: str) -> tuple[bytes, str]:
        response = self.client.get_object(self.bucket, key)
        try:
            content_type = response.headers.get("content-type", "application/octet-stream")
            return response.read(), content_type
        finally:
            response.close()
            response.release_conn()
