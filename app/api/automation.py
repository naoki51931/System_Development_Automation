import os
import tempfile
import uuid
from decimal import Decimal
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import (
    AuthenticatedUser,
    get_current_user,
    get_session,
    require_organization_access,
)
from app.errors import AppError
from app.models.automation import AISetting, ArtifactUploadIntent
from app.models.project import Artifact, ArtifactVersion, Project, Review, ReviewComment
from app.services.automation import (
    ResolvedAISetting,
    complete_upload,
    create_upload_intent,
    resolve_ai_setting,
    transition_comment,
    update_ai_setting,
)
from app.services.storage import (
    ALLOWED_MIME_TYPES,
    DEFAULT_MAX_FILE_SIZE,
    ArtifactStorage,
    LocalArtifactStorage,
)
from app.services.workflow import PROJECT_WRITE_ROLES

router = APIRouter(prefix="/api/v1", tags=["ai-storage-workflow"])


class AISettingCreate(BaseModel):
    organization_id: uuid.UUID
    project_id: uuid.UUID | None = None
    provider: str
    model: str = Field(min_length=1, max_length=100)
    operation_type: str
    enabled: bool = True
    review_threshold: int = Field(default=95, ge=0, le=100)
    max_auto_revision_count: int = Field(default=3, ge=0, le=10)
    minute_rate: Decimal = Field(
        default=Decimal("0"), ge=0, max_digits=18, decimal_places=8
    )
    token_input_rate: Decimal = Field(
        default=Decimal("0"), ge=0, max_digits=18, decimal_places=8
    )
    token_output_rate: Decimal = Field(
        default=Decimal("0"), ge=0, max_digits=18, decimal_places=8
    )
    currency: str = Field(default="JPY", pattern=r"^[A-Z]{3}$")


class AISettingUpdate(BaseModel):
    version: int = Field(ge=1)
    enabled: bool | None = None
    review_threshold: int | None = Field(default=None, ge=0, le=100)
    max_auto_revision_count: int | None = Field(default=None, ge=0, le=10)
    minute_rate: Decimal | None = Field(
        default=None, ge=0, max_digits=18, decimal_places=8
    )
    token_input_rate: Decimal | None = Field(
        default=None, ge=0, max_digits=18, decimal_places=8
    )
    token_output_rate: Decimal | None = Field(
        default=None, ge=0, max_digits=18, decimal_places=8
    )
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")


class UploadIntentRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    mime_type: str
    file_size: int = Field(ge=0)
    content_hash: str = Field(min_length=64, max_length=64)
    expires_seconds: int = Field(default=900, ge=60, le=3600)


class CompleteUploadRequest(BaseModel):
    pass


class CommentActionRequest(BaseModel):
    version: int = Field(ge=1)


def get_storage(request: Request) -> ArtifactStorage:
    storage = getattr(request.app.state, "artifact_storage", None)
    if storage is None:
        root = Path(
            os.getenv(
                "LOCAL_ARTIFACT_ROOT",
                str(Path(tempfile.gettempdir()) / "system-navigator-artifacts"),
            )
        )
        storage = LocalArtifactStorage(root)
        request.app.state.artifact_storage = storage
    return storage


def setting_json(setting: AISetting | ResolvedAISetting) -> dict[str, object]:
    return {
        "id": str(setting.id) if isinstance(setting, AISetting) else None,
        "organization_id": str(setting.organization_id)
        if isinstance(setting, AISetting)
        else None,
        "project_id": str(setting.project_id)
        if isinstance(setting, AISetting) and setting.project_id
        else None,
        "provider": setting.provider,
        "model": setting.model,
        "operation_type": setting.operation_type,
        "enabled": setting.enabled,
        "review_threshold": setting.review_threshold,
        "max_auto_revision_count": setting.max_auto_revision_count,
        "minute_rate": str(setting.minute_rate),
        "token_input_rate": str(setting.token_input_rate),
        "token_output_rate": str(setting.token_output_rate),
        "currency": setting.currency,
        "version": setting.version,
        "source": setting.source
        if isinstance(setting, ResolvedAISetting)
        else ("project" if setting.project_id else "organization"),
    }


@router.post("/ai-settings", status_code=status.HTTP_201_CREATED)
def post_ai_setting(
    payload: AISettingCreate,
    authenticated: Annotated[AuthenticatedUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    require_organization_access(
        payload.organization_id, authenticated, session, PROJECT_WRITE_ROLES
    )
    if payload.project_id is not None:
        project = session.get(Project, payload.project_id)
        if project is None:
            raise AppError("RESOURCE_NOT_FOUND", "Project not found")
        if project.organization_id != payload.organization_id:
            raise AppError(
                "PERMISSION_DENIED", "Project belongs to another organization"
            )
    setting = AISetting(**payload.model_dump())
    session.add(setting)
    session.commit()
    return setting_json(setting)


@router.get("/ai-settings/resolved")
def get_resolved_ai_setting(
    organization_id: uuid.UUID,
    provider: str,
    model: str,
    operation_type: str,
    authenticated: Annotated[AuthenticatedUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    project_id: uuid.UUID | None = None,
):
    require_organization_access(organization_id, authenticated, session)
    if project_id is not None:
        project = session.get(Project, project_id)
        if project is None or project.organization_id != organization_id:
            raise AppError("PERMISSION_DENIED", "Project access denied")
    return setting_json(
        resolve_ai_setting(
            session, organization_id, project_id, provider, model, operation_type
        )
    )


@router.patch("/ai-settings/{setting_id}")
def patch_ai_setting(
    setting_id: uuid.UUID,
    payload: AISettingUpdate,
    authenticated: Annotated[AuthenticatedUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    setting = session.get(AISetting, setting_id)
    if setting is None:
        raise AppError("RESOURCE_NOT_FOUND", "AI setting not found")
    require_organization_access(
        setting.organization_id, authenticated, session, PROJECT_WRITE_ROLES
    )
    values = payload.model_dump(exclude={"version"}, exclude_none=True)
    update_ai_setting(session, setting, payload.version, values)
    session.commit()
    return setting_json(setting)


@router.post(
    "/artifacts/{artifact_id}/upload-intents", status_code=status.HTTP_201_CREATED
)
def post_upload_intent(
    artifact_id: uuid.UUID,
    payload: UploadIntentRequest,
    authenticated: Annotated[AuthenticatedUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    storage: Annotated[ArtifactStorage, Depends(get_storage)],
):
    artifact = session.get(Artifact, artifact_id)
    if artifact is None:
        raise AppError("RESOURCE_NOT_FOUND", "Artifact not found")
    access = require_organization_access(
        artifact.organization_id, authenticated, session
    )
    if payload.mime_type not in ALLOWED_MIME_TYPES:
        raise AppError("UNSUPPORTED_MEDIA_TYPE", "Unsupported media type")
    if payload.file_size > DEFAULT_MAX_FILE_SIZE:
        raise AppError("FILE_TOO_LARGE", "File exceeds configured size limit")
    intent, upload_url = create_upload_intent(
        session, storage, artifact, access, **payload.model_dump()
    )
    session.commit()
    return {
        "version_id": str(intent.version_id),
        "upload_url": upload_url,
        "expires_seconds": payload.expires_seconds,
    }


@router.post("/artifact-versions/{version_id}/complete-upload")
def post_complete_upload(
    version_id: uuid.UUID,
    _payload: CompleteUploadRequest,
    authenticated: Annotated[AuthenticatedUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    storage: Annotated[ArtifactStorage, Depends(get_storage)],
):
    intent = session.scalar(
        select(ArtifactUploadIntent).where(
            ArtifactUploadIntent.version_id == version_id
        )
    )
    if intent is None:
        raise AppError("RESOURCE_NOT_FOUND", "Upload intent not found")
    artifact = session.get(Artifact, intent.artifact_id)
    if artifact is None:
        raise AppError("RESOURCE_NOT_FOUND", "Artifact not found")
    access = require_organization_access(intent.organization_id, authenticated, session)
    version = complete_upload(session, storage, intent, artifact, access)
    session.commit()
    return {
        "id": str(version.id),
        "version_number": version.version_number,
        "content_hash": version.content_hash,
    }


@router.get("/artifact-versions/{version_id}/download-url")
def get_download_url(
    version_id: uuid.UUID,
    authenticated: Annotated[AuthenticatedUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    storage: Annotated[ArtifactStorage, Depends(get_storage)],
    expires_seconds: int = 300,
):
    if expires_seconds < 60 or expires_seconds > 3600:
        raise AppError("INVALID_REQUEST", "Invalid URL expiry")
    version = session.get(ArtifactVersion, version_id)
    if version is None:
        raise AppError("RESOURCE_NOT_FOUND", "Artifact version not found")
    artifact = session.get(Artifact, version.artifact_id)
    if artifact is None:
        raise AppError("RESOURCE_NOT_FOUND", "Artifact not found")
    require_organization_access(artifact.organization_id, authenticated, session)
    return {
        "download_url": storage.create_download_url(
            version.storage_key, expires_seconds
        ),
        "expires_seconds": expires_seconds,
    }


def _comment_action(
    comment_id: uuid.UUID,
    action: str,
    payload: CommentActionRequest,
    authenticated: AuthenticatedUser,
    session: Session,
):
    comment = session.get(ReviewComment, comment_id)
    if comment is None:
        raise AppError("RESOURCE_NOT_FOUND", "Review comment not found")
    review = session.get(Review, comment.review_id)
    if review is None:
        raise AppError("RESOURCE_NOT_FOUND", "Review not found")
    access = require_organization_access(review.organization_id, authenticated, session)
    transition_comment(
        session, comment, review, access, action, uuid.uuid4(), payload.version
    )
    session.commit()
    return {
        "id": str(comment.id),
        "status": comment.status,
        "review_version": review.version,
    }


@router.post("/review-comments/{comment_id}/accept")
def accept_comment(
    comment_id: uuid.UUID,
    payload: CommentActionRequest,
    authenticated: Annotated[AuthenticatedUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    return _comment_action(comment_id, "accepted", payload, authenticated, session)


@router.post("/review-comments/{comment_id}/reject")
def reject_comment(
    comment_id: uuid.UUID,
    payload: CommentActionRequest,
    authenticated: Annotated[AuthenticatedUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    return _comment_action(comment_id, "rejected", payload, authenticated, session)


@router.post("/review-comments/{comment_id}/resolve")
def resolve_comment(
    comment_id: uuid.UUID,
    payload: CommentActionRequest,
    authenticated: Annotated[AuthenticatedUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    return _comment_action(comment_id, "resolved", payload, authenticated, session)
