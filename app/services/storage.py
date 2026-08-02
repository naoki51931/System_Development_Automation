import hashlib
import json
import re
import secrets
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from app.errors import AppError

ALLOWED_MIME_TYPES = frozenset({"text/plain", "text/markdown", "application/json", "application/pdf", "application/zip"})
DEFAULT_MAX_FILE_SIZE = 25 * 1024 * 1024
SAFE_FILENAME = re.compile(r"[^A-Za-z0-9._-]+")


@dataclass(frozen=True)
class ObjectMetadata:
    size: int
    mime_type: str
    content_hash: str


class ArtifactStorage(ABC):
    @abstractmethod
    def create_upload_url(self, storage_key: str, expires_seconds: int = 900) -> str: ...
    @abstractmethod
    def create_download_url(self, storage_key: str, expires_seconds: int = 300) -> str: ...
    @abstractmethod
    def put_object(self, storage_key: str, content: bytes, mime_type: str) -> ObjectMetadata: ...
    @abstractmethod
    def get_object(self, storage_key: str) -> bytes: ...
    @abstractmethod
    def head_object(self, storage_key: str) -> ObjectMetadata: ...
    @abstractmethod
    def delete_unapproved_object(self, storage_key: str, *, approved: bool) -> None: ...


class LocalArtifactStorage(ArtifactStorage):
    def __init__(self, root: str | Path, max_file_size: int = DEFAULT_MAX_FILE_SIZE):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.max_file_size = max_file_size

    @staticmethod
    def build_storage_key(organization_id: uuid.UUID, project_id: uuid.UUID, artifact_id: uuid.UUID, version_id: uuid.UUID, filename: str) -> str:
        if not filename or filename != PurePosixPath(filename).name or ".." in filename or "/" in filename or "\\" in filename:
            raise AppError("INVALID_REQUEST", "Invalid filename")
        safe = SAFE_FILENAME.sub("_", filename).strip("._")
        if not safe:
            raise AppError("INVALID_REQUEST", "Invalid filename")
        return f"organizations/{organization_id}/projects/{project_id}/artifacts/{artifact_id}/versions/{version_id}/{safe}"

    def _path(self, storage_key: str) -> Path:
        pure = PurePosixPath(storage_key)
        if pure.is_absolute() or ".." in pure.parts or not storage_key.startswith("organizations/"):
            raise AppError("INVALID_REQUEST", "Invalid storage key")
        path = (self.root / Path(*pure.parts)).resolve()
        if self.root not in path.parents:
            raise AppError("INVALID_REQUEST", "Invalid storage key")
        return path

    def _validate(self, content: bytes, mime_type: str) -> None:
        if mime_type not in ALLOWED_MIME_TYPES:
            raise AppError("UNSUPPORTED_MEDIA_TYPE", "Unsupported media type")
        if len(content) > self.max_file_size:
            raise AppError("FILE_TOO_LARGE", "File exceeds configured size limit")

    def create_upload_url(self, storage_key: str, expires_seconds: int = 900) -> str:
        self._path(storage_key)
        return f"local-upload://{secrets.token_urlsafe(24)}?expires={expires_seconds}"

    def create_download_url(self, storage_key: str, expires_seconds: int = 300) -> str:
        self.head_object(storage_key)
        return f"local-download://{secrets.token_urlsafe(24)}?expires={expires_seconds}"

    def put_object(self, storage_key: str, content: bytes, mime_type: str) -> ObjectMetadata:
        self._validate(content, mime_type)
        path = self._path(storage_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        metadata = ObjectMetadata(len(content), mime_type, hashlib.sha256(content).hexdigest())
        path.with_suffix(path.suffix + ".metadata").write_text(json.dumps(metadata.__dict__), encoding="utf-8")
        return metadata

    def get_object(self, storage_key: str) -> bytes:
        path = self._path(storage_key)
        if not path.is_file():
            raise AppError("RESOURCE_NOT_FOUND", "Stored object not found")
        return path.read_bytes()

    def head_object(self, storage_key: str) -> ObjectMetadata:
        path = self._path(storage_key)
        metadata_path = path.with_suffix(path.suffix + ".metadata")
        if not path.is_file() or not metadata_path.is_file():
            raise AppError("RESOURCE_NOT_FOUND", "Stored object not found")
        raw = json.loads(metadata_path.read_text(encoding="utf-8"))
        return ObjectMetadata(int(raw["size"]), str(raw["mime_type"]), str(raw["content_hash"]))

    def delete_unapproved_object(self, storage_key: str, *, approved: bool) -> None:
        if approved:
            raise AppError("INVALID_STATE_TRANSITION", "Approved artifact files cannot be deleted")
        path = self._path(storage_key)
        path.unlink(missing_ok=True)
        path.with_suffix(path.suffix + ".metadata").unlink(missing_ok=True)


class S3ArtifactStorageStub(ArtifactStorage):
    def _disabled(self, *args, **kwargs): raise AppError("AI_PROVIDER_UNAVAILABLE", "AWS S3 communication is disabled")
    create_upload_url = create_download_url = put_object = get_object = head_object = delete_unapproved_object = _disabled
