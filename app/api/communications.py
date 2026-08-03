import os
import uuid
from datetime import datetime, time, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.automation import get_storage
from app.api.pagination import paginate_query
from app.auth.dependencies import AuthenticatedUser, get_current_user, get_session, require_organization_access
from app.errors import AppError
from app.models.billing import Estimate
from app.models.communications import (
    ChangeRequest,
    ChangeRequestImpact,
    ChatMessage,
    ChatRoom,
    DocumentGenerationJob,
    EmailTemplate,
    Notification, NotificationDelivery,
    NotificationPreference,
)
from app.models.project import Artifact, ArtifactVersion, Project
from app.services.ai_providers import MockAIProvider
from app.services.communication_providers import EmailProvider, MockEmailProvider, MockNotificationProvider, NotificationProvider
from app.services.communications import (
    PRIVILEGED_PROJECT_ROLES,
    analyze_change_request,
    attach_chat_artifact,
    create_change_request,
    create_chat_room,
    create_email_message,
    create_notification,
    decide_change_request,
    delete_chat_message,
    edit_chat_message,
    generate_document,
    mark_notification_read,
    post_chat_message,
    require_project_chat_access,
    resolve_email_template,
    send_email_message,
    update_preference,
)
from app.services.storage import ArtifactStorage

router = APIRouter(prefix="/api/v1", tags=["notifications-documents-chat"])


class PreferenceUpdate(BaseModel):
    version: int = Field(ge=1)
    in_app_enabled: bool | None = None
    email_enabled: bool | None = None
    digest_mode: str | None = None
    quiet_hours_start: time | None = None
    quiet_hours_end: time | None = None
    timezone: str | None = None


class VersionInput(BaseModel):
    version: int = Field(ge=1)


class DocumentGenerateInput(BaseModel):
    document_type: str
    output_format: str = "pdf"
    source_id: uuid.UUID | None = None


class DocumentEmailInput(BaseModel):
    recipient_user_id: uuid.UUID
    template_code: str
    expires_seconds: int = Field(default=3600, ge=60, le=86400)
    deduplication_key: str = Field(min_length=8, max_length=255)


class ChatRoomInput(BaseModel):
    room_type: str
    name: str = Field(min_length=1, max_length=255)


class ChatMessageInput(BaseModel):
    body: str = Field(min_length=1, max_length=10000)
    message_type: str = "user"
    reply_to_message_id: uuid.UUID | None = None


class ChatEditInput(BaseModel):
    body: str = Field(min_length=1, max_length=10000)
    version: int = Field(ge=1)


class AttachmentInput(BaseModel):
    artifact_version_id: uuid.UUID
    filename: str = Field(min_length=1, max_length=255)


class ChangeRequestInput(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1, max_length=10000)
    priority: str = "normal"
    scope_type: str
    estimate_id: uuid.UUID | None = None


def get_email_provider(request: Request) -> EmailProvider:
    provider = getattr(request.app.state, "email_provider", None)
    if provider is None:
        outcomes = [value for value in os.getenv("MOCK_EMAIL_OUTCOMES", "delivered").split(",") if value]
        provider = MockEmailProvider(outcomes)
        request.app.state.email_provider = provider
    return provider


def get_notification_provider(request: Request) -> NotificationProvider:
    provider = getattr(request.app.state, "notification_provider", None)
    if provider is None:
        provider = MockNotificationProvider()
        request.app.state.notification_provider = provider
    return provider


def notification_json(item: Notification) -> dict[str, object]:
    return {
        "id": str(item.id), "organization_id": str(item.organization_id),
        "project_id": str(item.project_id) if item.project_id else None,
        "event_type": item.event_type, "title": item.title, "body": item.body,
        "severity": item.severity, "status": item.status, "action_url": item.action_url,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "read_at": item.read_at.isoformat() if item.read_at else None, "version": item.version,
    }


def preference_json(item: NotificationPreference) -> dict[str, object]:
    return {
        "id": str(item.id), "organization_id": str(item.organization_id), "user_id": str(item.user_id),
        "event_type": item.event_type, "in_app_enabled": item.in_app_enabled,
        "email_enabled": item.email_enabled, "digest_mode": item.digest_mode,
        "quiet_hours_start": item.quiet_hours_start.isoformat() if item.quiet_hours_start else None,
        "quiet_hours_end": item.quiet_hours_end.isoformat() if item.quiet_hours_end else None,
        "timezone": item.timezone, "version": item.version,
    }


def chat_room_json(room: ChatRoom) -> dict[str, object]:
    return {"id": str(room.id), "project_id": str(room.project_id), "room_type": room.room_type, "name": room.name, "status": room.status, "version": room.version}


def chat_message_json(message: ChatMessage) -> dict[str, object]:
    return {
        "id": str(message.id), "project_id": str(message.project_id), "chat_room_id": str(message.chat_room_id),
        "sender_user_id": str(message.sender_user_id) if message.sender_user_id else None,
        "message_type": message.message_type, "body": message.body, "status": message.status,
        "reply_to_message_id": str(message.reply_to_message_id) if message.reply_to_message_id else None,
        "created_at": message.created_at.isoformat() if message.created_at else None, "version": message.version,
    }


def change_request_json(item: ChangeRequest, session: Session) -> dict[str, object]:
    impacts = session.scalars(select(ChangeRequestImpact).where(ChangeRequestImpact.change_request_id == item.id)).all()
    return {
        "id": str(item.id), "project_id": str(item.project_id), "chat_message_id": str(item.chat_message_id),
        "title": item.title, "description": item.description, "status": item.status,
        "priority": item.priority, "scope_type": item.scope_type,
        "estimate_id": str(item.estimate_id) if item.estimate_id else None, "version": item.version,
        "impacts": [{"impact_type": value.impact_type, "description": value.description, "estimated_minutes": value.estimated_minutes, "estimated_amount": str(value.estimated_amount)} for value in impacts],
    }


def project_context(session: Session, project_id: uuid.UUID, authenticated: AuthenticatedUser):
    project = session.get(Project, project_id)
    if project is None:
        raise AppError("RESOURCE_NOT_FOUND", "Project not found")
    access = require_organization_access(project.organization_id, authenticated, session)
    return project, access


@router.get("/notifications")
def list_notifications(organization_id: uuid.UUID, authenticated: Annotated[AuthenticatedUser, Depends(get_current_user)], session: Annotated[Session, Depends(get_session)], cursor: str | None = None, page_size: int = Query(50, ge=1, le=100)):
    require_organization_access(organization_id, authenticated, session)
    statement = select(Notification).where(Notification.organization_id == organization_id, Notification.user_id == authenticated.user.id, Notification.status != "dismissed")
    return paginate_query(session, statement, Notification, cursor, page_size, notification_json)


@router.post("/notifications/{notification_id}/read")
def read_notification(notification_id: uuid.UUID, payload: VersionInput, authenticated: Annotated[AuthenticatedUser, Depends(get_current_user)], session: Annotated[Session, Depends(get_session)]):
    item = session.get(Notification, notification_id)
    if item is None:
        raise AppError("RESOURCE_NOT_FOUND", "Notification not found")
    access = require_organization_access(item.organization_id, authenticated, session)
    mark_notification_read(session, item, access, payload.version)
    session.commit()
    return notification_json(item)


@router.post("/notifications/read-all")
def read_all_notifications(organization_id: uuid.UUID, authenticated: Annotated[AuthenticatedUser, Depends(get_current_user)], session: Annotated[Session, Depends(get_session)]):
    require_organization_access(organization_id, authenticated, session)
    values = session.scalars(select(Notification).where(Notification.organization_id == organization_id, Notification.user_id == authenticated.user.id, Notification.status.in_(["pending", "delivered"]))).all()
    now = datetime.now(timezone.utc)
    for item in values:
        item.status = "read"
        item.read_at = now
    session.commit()
    return {"updated": len(values)}


@router.get("/notification-preferences")
def list_preferences(organization_id: uuid.UUID, authenticated: Annotated[AuthenticatedUser, Depends(get_current_user)], session: Annotated[Session, Depends(get_session)]):
    require_organization_access(organization_id, authenticated, session)
    values = session.scalars(select(NotificationPreference).where(NotificationPreference.organization_id == organization_id, NotificationPreference.user_id == authenticated.user.id).order_by(NotificationPreference.event_type)).all()
    return [preference_json(item) for item in values]


@router.patch("/notification-preferences/{preference_id}")
def patch_preference(preference_id: uuid.UUID, payload: PreferenceUpdate, authenticated: Annotated[AuthenticatedUser, Depends(get_current_user)], session: Annotated[Session, Depends(get_session)]):
    item = session.get(NotificationPreference, preference_id)
    if item is None:
        raise AppError("RESOURCE_NOT_FOUND", "Notification preference not found")
    access = require_organization_access(item.organization_id, authenticated, session)
    update_preference(session, item, access, payload.version, payload.model_dump(exclude={"version"}, exclude_none=True))
    session.commit()
    return preference_json(item)


@router.post("/projects/{project_id}/documents/generate", status_code=status.HTTP_201_CREATED)
def post_document(project_id: uuid.UUID, payload: DocumentGenerateInput, authenticated: Annotated[AuthenticatedUser, Depends(get_current_user)], session: Annotated[Session, Depends(get_session)], storage: Annotated[ArtifactStorage, Depends(get_storage)]):
    project, access = project_context(session, project_id, authenticated)
    job = generate_document(session, storage, project, access, **payload.model_dump())
    session.commit()
    return {"id": str(job.id), "status": job.status, "document_type": job.document_type, "output_format": job.output_format, "artifact_id": str(job.artifact_id), "artifact_version_id": str(job.artifact_version_id), "content_hash": job.content_hash, "file_size": job.file_size, "version": job.version}


@router.get("/document-generation-jobs/{job_id}")
def get_document_job(job_id: uuid.UUID, authenticated: Annotated[AuthenticatedUser, Depends(get_current_user)], session: Annotated[Session, Depends(get_session)]):
    job = session.get(DocumentGenerationJob, job_id)
    if job is None:
        raise AppError("RESOURCE_NOT_FOUND", "Document generation job not found")
    require_organization_access(job.organization_id, authenticated, session)
    return {"id": str(job.id), "status": job.status, "document_type": job.document_type, "output_format": job.output_format, "artifact_version_id": str(job.artifact_version_id) if job.artifact_version_id else None, "content_hash": job.content_hash, "file_size": job.file_size, "version": job.version}


@router.get("/artifact-versions/{version_id}/document-download-url")
def document_download_url(version_id: uuid.UUID, authenticated: Annotated[AuthenticatedUser, Depends(get_current_user)], session: Annotated[Session, Depends(get_session)], storage: Annotated[ArtifactStorage, Depends(get_storage)], expires_seconds: int = 3600):
    version = session.get(ArtifactVersion, version_id)
    if version is None:
        raise AppError("RESOURCE_NOT_FOUND", "Artifact version not found")
    artifact = session.get(Artifact, version.artifact_id)
    if artifact is None:
        raise AppError("RESOURCE_NOT_FOUND", "Artifact not found")
    require_organization_access(artifact.organization_id, authenticated, session)
    if expires_seconds < 60 or expires_seconds > 86400:
        raise AppError("INVALID_REQUEST", "Invalid URL expiry")
    job = session.scalar(select(DocumentGenerationJob.id).where(DocumentGenerationJob.artifact_version_id == version.id, DocumentGenerationJob.status == "completed"))
    if job is None:
        raise AppError("RESOURCE_NOT_FOUND", "Generated document not found")
    return {"download_url": storage.create_download_url(version.storage_key, expires_seconds), "expires_seconds": expires_seconds}


@router.post("/artifact-versions/{version_id}/send-email")
def send_document_email(version_id: uuid.UUID, payload: DocumentEmailInput, authenticated: Annotated[AuthenticatedUser, Depends(get_current_user)], session: Annotated[Session, Depends(get_session)], storage: Annotated[ArtifactStorage, Depends(get_storage)], provider: Annotated[EmailProvider, Depends(get_email_provider)]):
    version = session.get(ArtifactVersion, version_id)
    artifact = session.get(Artifact, version.artifact_id) if version else None
    if version is None or artifact is None:
        raise AppError("RESOURCE_NOT_FOUND", "Document not found")
    access = require_organization_access(artifact.organization_id, authenticated, session)
    if access.role_codes.isdisjoint(PRIVILEGED_PROJECT_ROLES):
        raise AppError("DOCUMENT_SEND_FORBIDDEN", "Document sending is forbidden")
    if artifact.status != "approved" or artifact.current_version_id != version.id:
        raise AppError("DOCUMENT_SEND_FORBIDDEN", "Only the approved current document can be sent")
    recipient = session.get(type(authenticated.user), payload.recipient_user_id)
    if recipient is None:
        raise AppError("INVALID_EMAIL_RECIPIENT", "Recipient not found")
    recipient_access = require_organization_access(artifact.organization_id, AuthenticatedUser(recipient), session)
    template = resolve_email_template(session, artifact.organization_id, payload.template_code)
    download_url = storage.create_download_url(version.storage_key, payload.expires_seconds)
    notification = create_notification(
        session, organization_id=artifact.organization_id, user_id=recipient.id, project_id=artifact.project_id,
        event_type="document_generated", title="Document ready", body=f"{artifact.title} is ready.", severity="info",
        action_url=f"/artifacts/{artifact.id}", deduplication_key=f"document-email:{payload.deduplication_key}",
    )
    email_delivery = session.scalar(select(NotificationDelivery).where(
        NotificationDelivery.notification_id == notification.id, NotificationDelivery.channel == "email",
    ))
    if email_delivery is None:
        email_delivery = NotificationDelivery(notification_id=notification.id, channel="email", provider="mock_email", status="scheduled", scheduled_at=datetime.now(timezone.utc), max_attempts=5)
        session.add(email_delivery)
    message = create_email_message(
        session, template, recipient, organization_id=artifact.organization_id, project_id=artifact.project_id,
        notification_id=notification.id, values={"service_name": "SystemNavigator AI", "user_name": recipient.display_name, "document_type": artifact.artifact_type, "download_url": download_url, "expires_at": str(payload.expires_seconds)},
        deduplication_key=payload.deduplication_key, scheduled_at=datetime.now(timezone.utc),
    )
    send_email_message(session, message, provider, datetime.now(timezone.utc))
    email_delivery.attempt_count = message.attempt_count
    email_delivery.provider_message_id = message.provider_message_id
    email_delivery.status = message.status
    email_delivery.sent_at = message.sent_at
    if message.status == "delivered":
        email_delivery.delivered_at = message.sent_at
    session.commit()
    return {"id": str(message.id), "status": message.status, "provider_message_id": message.provider_message_id}


@router.post("/projects/{project_id}/chat-rooms", status_code=status.HTTP_201_CREATED)
def post_room(project_id: uuid.UUID, payload: ChatRoomInput, authenticated: Annotated[AuthenticatedUser, Depends(get_current_user)], session: Annotated[Session, Depends(get_session)]):
    project, access = project_context(session, project_id, authenticated)
    room = create_chat_room(session, project, access, **payload.model_dump())
    session.commit()
    return chat_room_json(room)


@router.get("/projects/{project_id}/chat-rooms")
def list_rooms(project_id: uuid.UUID, authenticated: Annotated[AuthenticatedUser, Depends(get_current_user)], session: Annotated[Session, Depends(get_session)]):
    project, access = project_context(session, project_id, authenticated)
    require_project_chat_access(session, project, access)
    rooms = session.scalars(select(ChatRoom).where(ChatRoom.organization_id == project.organization_id, ChatRoom.project_id == project.id).order_by(ChatRoom.created_at)).all()
    return [chat_room_json(item) for item in rooms]


def room_context(session: Session, room_id: uuid.UUID, authenticated: AuthenticatedUser):
    room = session.get(ChatRoom, room_id)
    if room is None:
        raise AppError("CHAT_ROOM_NOT_FOUND", "Chat room not found")
    project = session.get(Project, room.project_id)
    if project is None:
        raise AppError("RESOURCE_NOT_FOUND", "Project not found")
    access = require_organization_access(room.organization_id, authenticated, session)
    require_project_chat_access(session, project, access)
    return room, project, access


@router.get("/chat-rooms/{room_id}/messages")
def list_messages(room_id: uuid.UUID, authenticated: Annotated[AuthenticatedUser, Depends(get_current_user)], session: Annotated[Session, Depends(get_session)], cursor: str | None = None, page_size: int = Query(50, ge=1, le=100)):
    room, _project, _access = room_context(session, room_id, authenticated)
    return paginate_query(session, select(ChatMessage).where(ChatMessage.chat_room_id == room.id), ChatMessage, cursor, page_size, chat_message_json)


@router.post("/chat-rooms/{room_id}/messages", status_code=status.HTTP_201_CREATED)
def post_message(room_id: uuid.UUID, payload: ChatMessageInput, authenticated: Annotated[AuthenticatedUser, Depends(get_current_user)], session: Annotated[Session, Depends(get_session)]):
    room, project, access = room_context(session, room_id, authenticated)
    message = post_chat_message(session, room, project, access, **payload.model_dump())
    session.commit()
    return chat_message_json(message)


@router.patch("/chat-messages/{message_id}")
def patch_message(message_id: uuid.UUID, payload: ChatEditInput, authenticated: Annotated[AuthenticatedUser, Depends(get_current_user)], session: Annotated[Session, Depends(get_session)]):
    message = session.get(ChatMessage, message_id)
    if message is None:
        raise AppError("RESOURCE_NOT_FOUND", "Chat message not found")
    access = require_organization_access(message.organization_id, authenticated, session)
    edit_chat_message(session, message, access, payload.body, payload.version)
    session.commit()
    return chat_message_json(message)


@router.delete("/chat-messages/{message_id}")
def remove_message(message_id: uuid.UUID, version: int, authenticated: Annotated[AuthenticatedUser, Depends(get_current_user)], session: Annotated[Session, Depends(get_session)]):
    message = session.get(ChatMessage, message_id)
    if message is None:
        raise AppError("RESOURCE_NOT_FOUND", "Chat message not found")
    access = require_organization_access(message.organization_id, authenticated, session)
    delete_chat_message(session, message, access, version)
    session.commit()
    return chat_message_json(message)


@router.post("/chat-messages/{message_id}/attachments", status_code=status.HTTP_201_CREATED)
def post_attachment(message_id: uuid.UUID, payload: AttachmentInput, authenticated: Annotated[AuthenticatedUser, Depends(get_current_user)], session: Annotated[Session, Depends(get_session)], storage: Annotated[ArtifactStorage, Depends(get_storage)]):
    message = session.get(ChatMessage, message_id)
    version = session.get(ArtifactVersion, payload.artifact_version_id)
    artifact = session.get(Artifact, version.artifact_id) if version else None
    if message is None or version is None or artifact is None:
        raise AppError("RESOURCE_NOT_FOUND", "Attachment resource not found")
    access = require_organization_access(message.organization_id, authenticated, session)
    attachment = attach_chat_artifact(session, storage, message, version, artifact, access, payload.filename)
    session.commit()
    return {"id": str(attachment.id), "filename": attachment.filename, "mime_type": attachment.mime_type, "file_size": attachment.file_size, "content_hash": attachment.content_hash}


@router.post("/chat-messages/{message_id}/change-requests", status_code=status.HTTP_201_CREATED)
def post_change_request(message_id: uuid.UUID, payload: ChangeRequestInput, authenticated: Annotated[AuthenticatedUser, Depends(get_current_user)], session: Annotated[Session, Depends(get_session)]):
    message = session.get(ChatMessage, message_id)
    if message is None:
        raise AppError("RESOURCE_NOT_FOUND", "Chat message not found")
    access = require_organization_access(message.organization_id, authenticated, session)
    request = create_change_request(session, message, access, **payload.model_dump())
    session.commit()
    return change_request_json(request, session)


@router.get("/change-requests/{change_request_id}")
def get_change_request(change_request_id: uuid.UUID, authenticated: Annotated[AuthenticatedUser, Depends(get_current_user)], session: Annotated[Session, Depends(get_session)]):
    item = session.get(ChangeRequest, change_request_id)
    if item is None:
        raise AppError("RESOURCE_NOT_FOUND", "Change request not found")
    require_organization_access(item.organization_id, authenticated, session)
    return change_request_json(item, session)


@router.post("/change-requests/{change_request_id}/analyze")
def analyze_request(change_request_id: uuid.UUID, payload: VersionInput, authenticated: Annotated[AuthenticatedUser, Depends(get_current_user)], session: Annotated[Session, Depends(get_session)]):
    item = session.get(ChangeRequest, change_request_id)
    if item is None:
        raise AppError("RESOURCE_NOT_FOUND", "Change request not found")
    access = require_organization_access(item.organization_id, authenticated, session)
    analyze_change_request(session, item, access, MockAIProvider([80]), payload.version)
    session.commit()
    return change_request_json(item, session)


def decide_request(change_request_id: uuid.UUID, action: str, payload: VersionInput, authenticated: AuthenticatedUser, session: Session):
    item = session.get(ChangeRequest, change_request_id)
    if item is None:
        raise AppError("RESOURCE_NOT_FOUND", "Change request not found")
    access = require_organization_access(item.organization_id, authenticated, session)
    decide_change_request(session, item, access, action, payload.version)
    session.commit()
    return change_request_json(item, session)


@router.post("/change-requests/{change_request_id}/approve")
def approve_request(change_request_id: uuid.UUID, payload: VersionInput, authenticated: Annotated[AuthenticatedUser, Depends(get_current_user)], session: Annotated[Session, Depends(get_session)]):
    return decide_request(change_request_id, "approve", payload, authenticated, session)


@router.post("/change-requests/{change_request_id}/reject")
def reject_request(change_request_id: uuid.UUID, payload: VersionInput, authenticated: Annotated[AuthenticatedUser, Depends(get_current_user)], session: Annotated[Session, Depends(get_session)]):
    return decide_request(change_request_id, "reject", payload, authenticated, session)
