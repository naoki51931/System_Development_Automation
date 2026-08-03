import hashlib


import html
import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from app.audit import record_audit_log
from app.auth.dependencies import OrganizationAccess, ensure_resource_organization
from app.errors import AppError
from app.models.billing import Contract, Estimate, EstimateItem
from app.models.communications import (
    ChangeRequest,
    ChangeRequestImpact,
    ChatAttachment,
    ChatMessage,
    ChatRoom,
    DocumentGenerationJob,
    DocumentTemplate,
    EmailMessage,
    EmailTemplate,
    Notification,
    NotificationDelivery,
    NotificationPreference,
    OutboxEvent,
)
from app.testing.faults import inject
from app.models.identity import Organization, User
from app.models.project import Artifact, ArtifactVersion, Project, ProjectMember
from app.services.ai_providers import AIProvider
from app.services.communication_providers import (
    EmailProvider,
    EmailProviderUnavailable,
    NotificationProvider,
    NotificationProviderUnavailable,
)
from app.services.storage import ALLOWED_MIME_TYPES, DEFAULT_MAX_FILE_SIZE, ArtifactStorage

SECURITY_EVENT_TYPES = frozenset({"payment_failed", "maintenance_suspended", "deletion_scheduled"})
ALLOWED_TEMPLATE_VARIABLES = frozenset({
    "service_name", "user_name", "organization_name", "project_name", "event_title",
    "event_body", "action_url", "download_url", "estimate_number", "contract_number",
    "document_type", "expires_at",
})
VARIABLE_PATTERN = re.compile(r"{{\s*([A-Za-z_][A-Za-z0-9_]*)\s*}}")
DANGEROUS_TEMPLATE_PATTERN = re.compile(r"{[%#]|__|\b(import|eval|exec|open|globals|class)\b", re.IGNORECASE)
HTML_TAG_PATTERN = re.compile(r"<[^>]+>")
SCRIPT_BLOCK_PATTERN = re.compile(r"<(script|style|iframe|object|embed)[^>]*>.*?</\1\s*>", re.IGNORECASE | re.DOTALL)
EXTERNAL_REFERENCE_PATTERN = re.compile(r"(?i)(https?://|file:|javascript:|data:text/html|src\s*=|url\s*\()")
SECRET_PATTERN = re.compile(
    r"(?i)(bearer\s+[A-Za-z0-9._-]+|postgres(?:ql)?://\S+|"
    r"(?:api[_-]?key|jwt|token|secret|password|card(?:_number)?|cvc)\s*[:=]\s*\S+)"
)
EMAIL_PATTERN = re.compile(r"^[^\s@\r\n]+@[^\s@\r\n]+\.[^\s@\r\n]+$")
PRIVILEGED_PROJECT_ROLES = frozenset({"organization_owner", "organization_admin", "project_manager", "reviewer"})
CHAT_MAX_LENGTH = 10000


def sanitize_sensitive(text: str) -> str:
    return SECRET_PATTERN.sub("[REDACTED]", text)


def sanitize_plain_text(text: str, *, maximum: int = CHAT_MAX_LENGTH) -> str:
    value = html.unescape(text)
    value = SCRIPT_BLOCK_PATTERN.sub("", value)
    value = HTML_TAG_PATTERN.sub("", value)
    value = sanitize_sensitive(value).strip()
    if not value or len(value) > maximum:
        raise AppError("INVALID_CHAT_MESSAGE", "Message body is invalid")
    return value


def sanitize_html(value: str) -> str:
    clean = SCRIPT_BLOCK_PATTERN.sub("", value)
    clean = re.sub(r"(?i)\son[a-z]+\s*=\s*[^ >]+", "", clean)
    clean = re.sub(r"(?i)(href|src)\s*=\s*[^ >]+", r"\1=#", clean)
    clean = sanitize_sensitive(clean)
    return clean


def validate_internal_url(value: str | None) -> str | None:
    if value is None:
        return None
    if not value.startswith("/") or value.startswith("//") or "\\" in value or re.search(r"(?i)javascript:|https?://", value):
        raise AppError("INVALID_REQUEST", "Action URL must be an internal relative URL")
    return value


def validate_timezone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError as exc:
        raise AppError("INVALID_REQUEST", "Timezone must be a valid IANA name") from exc


def scheduled_delivery_time(preference: NotificationPreference | None, now: datetime, severity: str) -> datetime | None:
    if severity == "critical":
        return now
    if preference is None:
        return now
    if preference.digest_mode == "none":
        return None
    local = now.astimezone(validate_timezone(preference.timezone))
    start, end = preference.quiet_hours_start, preference.quiet_hours_end
    if start is not None and end is not None:
        current = local.timetz().replace(tzinfo=None)
        quiet = start <= current < end if start < end else current >= start or current < end
        if quiet:
            end_date = local.date()
            if start >= end and current >= start:
                end_date += timedelta(days=1)
            local = datetime.combine(end_date, end, tzinfo=local.tzinfo)
    if preference.digest_mode == "hourly":
        local = local.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    elif preference.digest_mode == "daily":
        local = (local + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
    return local.astimezone(timezone.utc)


def check_version(resource, expected_version: int) -> None:
    if resource.version != expected_version:
        raise AppError("VERSION_CONFLICT", "Resource was updated by another request")


def safe_flush(session: Session) -> None:
    try:
        session.flush()
    except StaleDataError as exc:
        raise AppError("VERSION_CONFLICT", "Resource was updated by another request") from exc


def update_preference(session: Session, preference: NotificationPreference, access: OrganizationAccess, expected_version: int, values: dict) -> NotificationPreference:
    ensure_resource_organization(access, preference.organization_id)
    if preference.user_id != access.user.id and access.role_codes.isdisjoint(PRIVILEGED_PROJECT_ROLES):
        raise AppError("PERMISSION_DENIED", "Preference access denied")
    check_version(preference, expected_version)
    allowed = {"in_app_enabled", "email_enabled", "digest_mode", "quiet_hours_start", "quiet_hours_end", "timezone"}
    if set(values) - allowed:
        raise AppError("INVALID_REQUEST", "Unsupported preference field")
    if "timezone" in values:
        validate_timezone(values["timezone"])
    if preference.event_type in SECURITY_EVENT_TYPES:
        values["in_app_enabled"] = True
        if values.get("digest_mode") == "none":
            values["digest_mode"] = "immediate"
    for key, value in values.items():
        setattr(preference, key, value)
    safe_flush(session)
    return preference


def create_notification(
    session: Session,
    *,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    project_id: uuid.UUID | None,
    event_type: str,
    title: str,
    body: str,
    severity: str,
    action_url: str | None,
    deduplication_key: str,
    now: datetime | None = None,
    request_id: uuid.UUID | None = None,
) -> Notification:
    existing = session.scalar(select(Notification).where(
        Notification.organization_id == organization_id,
        Notification.user_id == user_id,
        Notification.deduplication_key == deduplication_key,
    ))
    if existing:
        raise AppError("DUPLICATE_NOTIFICATION", "Notification already exists")
    now = now or datetime.now(timezone.utc)
    clean_title = sanitize_sensitive(sanitize_plain_text(title, maximum=255))
    clean_body = sanitize_sensitive(sanitize_plain_text(body, maximum=5000))
    notification = Notification(
        organization_id=organization_id, user_id=user_id, project_id=project_id,
        event_type=event_type, title=clean_title, body=clean_body, severity=severity,
        status="pending", action_url=validate_internal_url(action_url),
        deduplication_key=deduplication_key,
    )
    session.add(notification)
    session.flush()
    preference = session.scalar(select(NotificationPreference).where(
        NotificationPreference.organization_id == organization_id,
        NotificationPreference.user_id == user_id,
        NotificationPreference.event_type == event_type,
    ))
    scheduled = scheduled_delivery_time(preference, now, severity)
    in_app = preference.in_app_enabled if preference else True
    if severity == "critical":
        in_app = True
    if in_app and scheduled is not None:
        session.add(NotificationDelivery(notification_id=notification.id, channel="in_app", provider="in_app", status="scheduled", scheduled_at=scheduled, max_attempts=5))
    if preference and preference.email_enabled and scheduled is not None:
        session.add(NotificationDelivery(notification_id=notification.id, channel="email", provider="mock_email", status="scheduled", scheduled_at=scheduled, max_attempts=5))
    if severity == "critical":
        record_audit_log(
            session, organization_id=organization_id, actor_user_id=None,
            action="notification.critical_created", resource_type="notification",
            resource_id=notification.id, request_id=request_id or uuid.uuid4(),
            after={"event_type": event_type, "severity": severity},
        )
    session.flush()
    return notification


def mark_notification_read(session: Session, notification: Notification, access: OrganizationAccess, expected_version: int) -> Notification:
    ensure_resource_organization(access, notification.organization_id)
    if notification.user_id != access.user.id:
        raise AppError("PERMISSION_DENIED", "Notification access denied")
    check_version(notification, expected_version)
    if notification.status in {"dismissed", "expired"}:
        raise AppError("INVALID_STATE_TRANSITION", "Notification cannot be read")
    notification.status = "read"
    notification.read_at = datetime.now(timezone.utc)
    safe_flush(session)
    return notification


def deliver_notification(session: Session, delivery: NotificationDelivery, provider: NotificationProvider, now: datetime) -> NotificationDelivery:
    if delivery.status == "delivered":
        return delivery
    if delivery.attempt_count >= delivery.max_attempts or delivery.scheduled_at > now:
        return delivery
    notification = session.get(Notification, delivery.notification_id)
    if notification is None:
        raise AppError("RESOURCE_NOT_FOUND", "Notification not found")
    delivery.attempt_count += 1
    try:
        result = provider.send(recipient_reference=str(notification.user_id), title=notification.title, body=notification.body)
        delivery.provider_message_id = result.provider_message_id
        delivery.status = result.status
        delivery.sent_at = now
        if result.status == "delivered":
            delivery.delivered_at = now
            notification.status = "delivered"
    except NotificationProviderUnavailable:
        delivery.status = "failed"
        delivery.failure_code = "PROVIDER_UNAVAILABLE"
        delivery.failure_message_sanitized = "Notification provider unavailable"
        delay = min(3600, 2 ** delivery.attempt_count * 60)
        delivery.scheduled_at = now + timedelta(seconds=delay)
    return delivery


def resolve_email_template(session: Session, organization_id: uuid.UUID, template_code: str, locale: str = "ja") -> EmailTemplate:
    template = session.scalar(select(EmailTemplate).where(
        EmailTemplate.organization_id == organization_id, EmailTemplate.template_code == template_code,
        EmailTemplate.locale == locale, EmailTemplate.status == "approved",
    ).order_by(EmailTemplate.version_number.desc()))
    if template is None:
        template = session.scalar(select(EmailTemplate).where(
            EmailTemplate.organization_id.is_(None), EmailTemplate.template_code == template_code,
            EmailTemplate.locale == locale, EmailTemplate.status == "approved",
        ).order_by(EmailTemplate.version_number.desc()))
    if template is None:
        raise AppError("TEMPLATE_NOT_FOUND", "Email template not found")
    return template


def render_template(source: str, values: dict[str, str], *, html_output: bool = False) -> str:
    if DANGEROUS_TEMPLATE_PATTERN.search(source):
        raise AppError("INVALID_TEMPLATE_DATA", "Template contains unsupported expressions")
    referenced = set(VARIABLE_PATTERN.findall(source))
    if referenced - ALLOWED_TEMPLATE_VARIABLES or set(values) - ALLOWED_TEMPLATE_VARIABLES:
        raise AppError("INVALID_TEMPLATE_DATA", "Template variable is not allowed")
    if EXTERNAL_REFERENCE_PATTERN.search(source):
        raise AppError("INVALID_TEMPLATE_DATA", "External references are forbidden")
    escaped = {key: html.escape(sanitize_sensitive(str(value))) for key, value in values.items()}
    try:
        rendered = VARIABLE_PATTERN.sub(lambda match: escaped.get(match.group(1), "未設定"), source)
    except Exception as exc:
        raise AppError("TEMPLATE_RENDER_FAILED", "Template rendering failed") from exc
    return sanitize_html(rendered) if html_output else html.unescape(HTML_TAG_PATTERN.sub("", rendered))


def validate_recipient(email: str) -> str:
    if not EMAIL_PATTERN.fullmatch(email) or "\r" in email or "\n" in email:
        raise AppError("INVALID_EMAIL_RECIPIENT", "Email recipient is invalid")
    return email.lower()


def create_email_message(
    session: Session,
    template: EmailTemplate,
    recipient: User,
    *,
    organization_id: uuid.UUID,
    project_id: uuid.UUID | None,
    notification_id: uuid.UUID | None,
    values: dict[str, str],
    deduplication_key: str,
    scheduled_at: datetime,
) -> EmailMessage:
    existing = session.scalar(select(EmailMessage).where(
        EmailMessage.organization_id == organization_id,
        EmailMessage.deduplication_key == deduplication_key,
    ))
    if existing:
        return existing
    subject = render_template(template.subject_template, values)
    if "\r" in subject or "\n" in subject:
        raise AppError("INVALID_TEMPLATE_DATA", "Email subject contains invalid characters")
    body_text = render_template(template.body_text_template, values)
    body_html = render_template(template.body_html_template, values, html_output=True) if template.body_html_template else None
    message = EmailMessage(
        organization_id=organization_id, project_id=project_id, notification_id=notification_id,
        template_id=template.id, recipient_user_id=recipient.id,
        recipient_email_snapshot=validate_recipient(recipient.email),
        subject_snapshot=subject, body_text_snapshot=body_text, body_html_snapshot=body_html,
        status="queued", scheduled_at=scheduled_at, attempt_count=0, deduplication_key=deduplication_key,
    )
    session.add(message)
    session.flush()
    return message


def send_email_message(session: Session, message: EmailMessage, provider: EmailProvider, now: datetime) -> EmailMessage:
    if message.status in {"sent", "delivered"}:
        return message
    if message.scheduled_at > now:
        return message
    message.attempt_count += 1
    try:
        result = provider.send_email(
            recipient=message.recipient_email_snapshot, subject=message.subject_snapshot,
            body_text=message.body_text_snapshot, body_html=message.body_html_snapshot,
        )
        message.provider_message_id = result.provider_message_id
        message.status = result.status
        message.sent_at = now
    except EmailProviderUnavailable:
        message.status = "failed"
        message.failure_code = "EMAIL_PROVIDER_UNAVAILABLE"
        message.failure_message_sanitized = "Email provider unavailable"
    return message


def _pdf_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def generate_local_pdf(text: str) -> bytes:
    safe = sanitize_sensitive(text)
    if EXTERNAL_REFERENCE_PATTERN.search(safe):
        raise AppError("INVALID_TEMPLATE_DATA", "External references are forbidden")
    ascii_text = safe.encode("ascii", "replace").decode("ascii")
    lines = ascii_text.splitlines()[:100]
    operations = ["BT /F1 10 Tf 50 780 Td"]
    for index, line in enumerate(lines):
        if index:
            operations.append("0 -14 Td")
        operations.append(f"({_pdf_escape(line[:120])}) Tj")
    operations.append("ET")
    stream = "\n".join(operations).encode()
    objects = [
        b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n",
        b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n",
        b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >> endobj\n",
        b"4 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n",
        f"5 0 obj << /Length {len(stream)} >> stream\n".encode() + stream + b"\nendstream endobj\n",
    ]
    output = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for obj in objects:
        offsets.append(len(output))
        output.extend(obj)
    xref = len(output)
    output.extend(f"xref\n0 {len(objects)+1}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode())
    output.extend(f"trailer << /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return bytes(output)


def _estimate_document(session: Session, estimate: Estimate, project: Project, organization: Organization) -> str:
    if estimate.status != "approved":
        raise AppError("DOCUMENT_GENERATION_FAILED", "Approved estimate is required")
    items = session.scalars(select(EstimateItem).where(EstimateItem.estimate_id == estimate.id).order_by(EstimateItem.display_order)).all()
    lines = [
        "SystemNavigator AI - Estimate", f"Estimate number: {estimate.estimate_number}",
        f"Customer organization: {organization.name}", f"Project: {project.name}",
        f"Created: {estimate.created_at.date() if estimate.created_at else '未設定'}",
        f"Valid until: {estimate.valid_until}", "Items:",
    ]
    lines += [f"- {item.description}: {item.quantity} {item.unit} x {item.unit_price} = {item.amount}" for item in items]
    lines += [f"Subtotal: {estimate.subtotal}", f"Tax: {estimate.tax_amount}", f"Total: {estimate.total_amount}", f"Currency: {estimate.currency}", "Notes: 未設定"]
    return "\n".join(lines)


def _contract_document(session: Session, contract: Contract, project: Project, organization: Organization) -> str:
    estimate = session.get(Estimate, contract.estimate_id)
    if estimate is None:
        raise AppError("DOCUMENT_GENERATION_FAILED", "Contract estimate is unavailable")
    return "\n".join([
        "SystemNavigator AI - Contract", f"Contract number: {contract.contract_number}",
        f"Contract type: {contract.contract_type}", f"Customer organization: {organization.name}",
        f"Project: {project.name}", f"Estimate number: {estimate.estimate_number}",
        f"Contract amount: {estimate.total_amount} {estimate.currency}", f"Terms version: {contract.terms_version}",
        f"Customer accepted by: {contract.customer_accepted_by_user_id or '未設定'}",
        f"Customer accepted at: {contract.customer_accepted_at or '未設定'}",
        f"Provider accepted by: {contract.provider_accepted_by_user_id or '未設定'}",
        f"Provider accepted at: {contract.provider_accepted_at or '未設定'}",
        f"Started at: {contract.started_at or '未設定'}",
    ])


def _basic_design_document(project: Project) -> str:
    return "\n".join([
        "SystemNavigator AI - Basic Design", f"Project: {project.name}",
        f"Overview: {project.description or '未設定'}", "Purpose: 未設定", "Target users: 未設定",
        "System architecture: 未設定", "Main screens: 未設定", "Main APIs: 未設定",
        "Main tables: 未設定", "AI review policy: 未設定", "Human review policy: 未設定",
        "Non-functional requirements: 未設定", "Revision history: 未設定",
    ])


def generate_document(
    session: Session,
    storage: ArtifactStorage,
    project: Project,
    access: OrganizationAccess,
    *,
    document_type: str,
    output_format: str,
    source_id: uuid.UUID | None = None,
) -> DocumentGenerationJob:
    ensure_resource_organization(access, project.organization_id)
    organization = session.get(Organization, project.organization_id)
    if organization is None:
        raise AppError("RESOURCE_NOT_FOUND", "Organization not found")
    authoritative = {"project_id": str(project.id), "document_type": document_type, "output_format": output_format, "source_id": str(source_id) if source_id else None}
    payload_hash = hashlib.sha256(json.dumps(authoritative, sort_keys=True).encode()).hexdigest()
    existing = session.scalar(select(DocumentGenerationJob).where(
        DocumentGenerationJob.organization_id == project.organization_id,
        DocumentGenerationJob.project_id == project.id,
        DocumentGenerationJob.document_type == document_type,
        DocumentGenerationJob.output_format == output_format,
        DocumentGenerationJob.input_payload_hash == payload_hash,
        DocumentGenerationJob.status == "completed",
    ))
    if existing:
        raise AppError("DOCUMENT_ALREADY_GENERATED", "Document was already generated")
    if output_format not in {"pdf", "html", "markdown"}:
        raise AppError("DOCUMENT_GENERATION_FAILED", "Output format is not implemented")
    if document_type == "estimate":
        estimate = session.get(Estimate, source_id)
        if estimate is None or estimate.organization_id != project.organization_id or estimate.project_id != project.id:
            raise AppError("DOCUMENT_GENERATION_FAILED", "Estimate source is invalid")
        text = _estimate_document(session, estimate, project, organization)
        artifact_type = "estimate"
    elif document_type == "contract":
        contract = session.get(Contract, source_id)
        if contract is None or contract.organization_id != project.organization_id or contract.project_id != project.id:
            raise AppError("DOCUMENT_GENERATION_FAILED", "Contract source is invalid")
        text = _contract_document(session, contract, project, organization)
        artifact_type = "detailed_design"
    elif document_type == "basic_design":
        text = _basic_design_document(project)
        artifact_type = "basic_design"
    else:
        raise AppError("DOCUMENT_GENERATION_FAILED", "Document type is not implemented")
    job = DocumentGenerationJob(
        organization_id=project.organization_id, project_id=project.id, document_type=document_type,
        status="processing", output_format=output_format, input_payload_hash=payload_hash,
        attempt_count=1, max_attempts=3, started_at=datetime.now(timezone.utc),
    )
    session.add(job)
    session.flush()
    artifact = Artifact(
        organization_id=project.organization_id, project_id=project.id, artifact_type=artifact_type,
        title=f"{document_type} document", status="draft", created_by_user_id=access.user.id,
    )
    session.add(artifact)
    session.flush()
    version_id = uuid.uuid4()
    extension = "pdf" if output_format == "pdf" else "html" if output_format == "html" else "md"
    mime = "application/pdf" if output_format == "pdf" else "text/plain"
    # Fail before storage or DB publication. The request transaction rolls back all
    # pending job/artifact rows and never exposes a partial artifact version.
    inject("DOCUMENT_RENDER_FAILURE")
    content = generate_local_pdf(text) if output_format == "pdf" else (f"<html><body><pre>{html.escape(text)}</pre></body></html>".encode() if output_format == "html" else text.encode())
    key = storage.build_storage_key(project.organization_id, project.id, artifact.id, version_id, f"{document_type}.{extension}")  # type: ignore[attr-defined]
    metadata = storage.put_object(key, content, mime)
    version = ArtifactVersion(
        id=version_id, artifact_id=artifact.id, version_number=1, storage_key=key,
        content_hash=metadata.content_hash, mime_type=metadata.mime_type, file_size=metadata.size,
        generated_by="human", created_by_user_id=access.user.id, change_summary="Locally generated document",
    )
    session.add(version)
    session.flush()
    artifact.current_version_id = version.id
    job.artifact_id = artifact.id
    job.artifact_version_id = version.id
    job.storage_key = key
    job.content_hash = metadata.content_hash
    job.file_size = metadata.size
    job.status = "completed"
    job.completed_at = datetime.now(timezone.utc)
    session.flush()
    emit_project_event(session, project, event_type="document_generated", title="Document generated", body=f"{document_type} document was generated.", severity="success", action_url=f"/artifacts/{artifact.id}", actor_user_id=access.user.id, aggregate_type="document_generation_job", aggregate_id=job.id)
    return job


def require_project_chat_access(session: Session, project: Project, access: OrganizationAccess) -> None:
    ensure_resource_organization(access, project.organization_id)
    if not access.role_codes.isdisjoint(PRIVILEGED_PROJECT_ROLES):
        return
    member = session.scalar(select(ProjectMember.id).where(
        ProjectMember.project_id == project.id, ProjectMember.user_id == access.user.id, ProjectMember.status == "active",
    ))
    if member is None:
        raise AppError("CHAT_ACCESS_FORBIDDEN", "Project chat access denied")


def create_chat_room(session: Session, project: Project, access: OrganizationAccess, *, room_type: str, name: str) -> ChatRoom:
    require_project_chat_access(session, project, access)
    room = ChatRoom(
        organization_id=project.organization_id, project_id=project.id, room_type=room_type,
        name=sanitize_plain_text(name, maximum=255), status="active", created_by_user_id=access.user.id,
    )
    session.add(room)
    session.flush()
    return room


def post_chat_message(session: Session, room: ChatRoom, project: Project, access: OrganizationAccess, *, body: str, message_type: str = "user", reply_to_message_id: uuid.UUID | None = None) -> ChatMessage:
    require_project_chat_access(session, project, access)
    if room.organization_id != project.organization_id or room.project_id != project.id:
        raise AppError("CHAT_ACCESS_FORBIDDEN", "Chat room scope mismatch")
    if room.status != "active":
        raise AppError("INVALID_CHAT_STATE", "Chat room is not active")
    if message_type in {"ai", "system"}:
        raise AppError("CHAT_ACCESS_FORBIDDEN", "Human users cannot post as AI or system")
    if reply_to_message_id:
        parent = session.get(ChatMessage, reply_to_message_id)
        if parent is None or parent.chat_room_id != room.id:
            raise AppError("INVALID_CHAT_MESSAGE", "Reply target is invalid")
    message = ChatMessage(
        organization_id=room.organization_id, project_id=room.project_id, chat_room_id=room.id,
        sender_user_id=access.user.id, message_type=message_type, body=sanitize_plain_text(body),
        status="active", reply_to_message_id=reply_to_message_id,
    )
    session.add(message)
    session.flush()
    emit_project_event(session, project, event_type="chat_message_received", title="New chat message", body="A new project chat message was posted.", severity="info", action_url=f"/chat-rooms/{room.id}", actor_user_id=access.user.id, aggregate_type="chat_message", aggregate_id=message.id)
    return message


def post_ai_chat_message(session: Session, room: ChatRoom, body: str) -> ChatMessage:
    message = ChatMessage(
        organization_id=room.organization_id, project_id=room.project_id, chat_room_id=room.id,
        sender_user_id=None, message_type="ai", body=sanitize_plain_text(body), status="active",
    )
    session.add(message)
    session.flush()
    return message


def edit_chat_message(session: Session, message: ChatMessage, access: OrganizationAccess, body: str, expected_version: int) -> ChatMessage:
    ensure_resource_organization(access, message.organization_id)
    if message.sender_user_id != access.user.id:
        raise AppError("CHAT_ACCESS_FORBIDDEN", "Only the sender can edit a message")
    check_version(message, expected_version)
    if message.status == "deleted":
        raise AppError("INVALID_CHAT_STATE", "Deleted messages cannot be edited")
    message.body = sanitize_plain_text(body)
    message.status = "edited"
    message.edited_at = datetime.now(timezone.utc)
    safe_flush(session)
    return message


def delete_chat_message(session: Session, message: ChatMessage, access: OrganizationAccess, expected_version: int) -> ChatMessage:
    ensure_resource_organization(access, message.organization_id)
    if message.sender_user_id != access.user.id and access.role_codes.isdisjoint(PRIVILEGED_PROJECT_ROLES):
        raise AppError("CHAT_ACCESS_FORBIDDEN", "Message deletion is forbidden")
    check_version(message, expected_version)
    message.body = "[deleted]"
    message.status = "deleted"
    message.deleted_at = datetime.now(timezone.utc)
    safe_flush(session)
    return message


def attach_chat_artifact(session: Session, storage: ArtifactStorage, message: ChatMessage, version: ArtifactVersion, artifact: Artifact, access: OrganizationAccess, filename: str) -> ChatAttachment:
    ensure_resource_organization(access, message.organization_id)
    if artifact.organization_id != message.organization_id or artifact.project_id != message.project_id or version.artifact_id != artifact.id:
        raise AppError("CHAT_ACCESS_FORBIDDEN", "Attachment scope mismatch")
    metadata = storage.head_object(version.storage_key)
    if metadata.mime_type not in ALLOWED_MIME_TYPES:
        raise AppError("UNSUPPORTED_ATTACHMENT_TYPE", "Attachment type is unsupported")
    if metadata.size > DEFAULT_MAX_FILE_SIZE:
        raise AppError("ATTACHMENT_TOO_LARGE", "Attachment is too large")
    if metadata.content_hash != version.content_hash or metadata.size != version.file_size or metadata.mime_type != version.mime_type:
        raise AppError("HASH_MISMATCH", "Attachment metadata does not match")
    safe_filename = filename.replace("\\", "/").split("/")[-1]
    if not safe_filename or safe_filename in {".", ".."}:
        raise AppError("INVALID_REQUEST", "Attachment filename is invalid")
    attachment = ChatAttachment(
        organization_id=message.organization_id, project_id=message.project_id,
        chat_message_id=message.id, artifact_version_id=version.id, filename=safe_filename,
        mime_type=metadata.mime_type, file_size=metadata.size, content_hash=metadata.content_hash,
    )
    session.add(attachment)
    session.flush()
    return attachment


def create_change_request(session: Session, message: ChatMessage, access: OrganizationAccess, *, title: str, description: str, priority: str, scope_type: str, estimate_id: uuid.UUID | None = None) -> ChangeRequest:
    ensure_resource_organization(access, message.organization_id)
    if message.sender_user_id != access.user.id and access.role_codes.isdisjoint(PRIVILEGED_PROJECT_ROLES):
        raise AppError("CHAT_ACCESS_FORBIDDEN", "Change request access denied")
    if estimate_id:
        estimate = session.get(Estimate, estimate_id)
        if estimate is None or estimate.organization_id != message.organization_id or estimate.project_id != message.project_id:
            raise AppError("INVALID_REQUEST", "Estimate scope mismatch")
    request = ChangeRequest(
        organization_id=message.organization_id, project_id=message.project_id,
        chat_message_id=message.id, requested_by_user_id=access.user.id,
        title=sanitize_plain_text(title, maximum=255), description=sanitize_plain_text(description),
        status="draft", priority=priority, scope_type=scope_type, estimate_id=estimate_id,
    )
    session.add(request)
    session.flush()
    project = session.get(Project, request.project_id)
    if project is not None:
        emit_project_event(session, project, event_type="change_request_submitted", title="Change request submitted", body=f"Change request {request.title} was submitted.", severity="info", action_url=f"/change-requests/{request.id}", actor_user_id=access.user.id, aggregate_type="change_request", aggregate_id=request.id)
    return request


def analyze_change_request(session: Session, request: ChangeRequest, access: OrganizationAccess, provider: AIProvider, expected_version: int) -> ChangeRequest:
    ensure_resource_organization(access, request.organization_id)
    check_version(request, expected_version)
    if request.status != "draft":
        raise AppError("INVALID_STATE_TRANSITION", "Change request cannot be analyzed")
    request.status = "analyzing"
    result = provider.review(request.description.encode())
    impact_type = {"bug": "test", "infrastructure": "infrastructure", "major_change": "schedule", "new_feature": "cost"}.get(request.scope_type, "document")
    session.add(ChangeRequestImpact(
        change_request_id=request.id, impact_type=impact_type,
        target_reference=None, description=f"Mock AI analysis; score={result.score if result.score is not None else '未設定'}. Human verification required.",
        estimated_minutes=max(30, result.input_tokens * 2), estimated_amount=Decimal("0"),
    ))
    request.status = "awaiting_customer_approval"
    safe_flush(session)
    return request


def decide_change_request(session: Session, request: ChangeRequest, access: OrganizationAccess, action: str, expected_version: int) -> ChangeRequest:
    ensure_resource_organization(access, request.organization_id)
    check_version(request, expected_version)
    if "customer" not in access.role_codes and access.role_codes.isdisjoint({"organization_owner", "organization_admin"}):
        raise AppError("PERMISSION_DENIED", "Customer approval is required")
    if request.status != "awaiting_customer_approval":
        raise AppError("INVALID_STATE_TRANSITION", "Change request is not awaiting approval")
    if action == "approve":
        impacts = session.scalar(select(ChangeRequestImpact.id).where(ChangeRequestImpact.change_request_id == request.id))
        if request.scope_type in {"major_change", "new_feature", "infrastructure"} and impacts is None:
            raise AppError("INVALID_STATE_TRANSITION", "Human review of major impact is required")
        request.status = "approved"
        request.approved_by_user_id = access.user.id
        request.approved_at = datetime.now(timezone.utc)
    elif action == "reject":
        request.status = "rejected"
    else:
        raise AppError("INVALID_REQUEST", "Unknown decision")
    safe_flush(session)
    if request.status == "approved":
        project = session.get(Project, request.project_id)
        if project is not None:
            emit_project_event(session, project, event_type="change_request_approved", title="Change request approved", body=f"Change request {request.title} was approved.", severity="success", action_url=f"/change-requests/{request.id}", actor_user_id=access.user.id, aggregate_type="change_request", aggregate_id=request.id)
    return request


def enqueue_outbox_event(session: Session, *, organization_id: uuid.UUID, event_type: str, aggregate_type: str, aggregate_id: uuid.UUID, payload: dict, now: datetime | None = None) -> OutboxEvent:
    payload_hash = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    existing = session.scalar(select(OutboxEvent).where(
        OutboxEvent.organization_id == organization_id, OutboxEvent.event_type == event_type,
        OutboxEvent.aggregate_type == aggregate_type, OutboxEvent.aggregate_id == aggregate_id,
        OutboxEvent.payload_hash == payload_hash,
    ))
    if existing:
        return existing
    event = OutboxEvent(
        organization_id=organization_id, event_type=event_type, aggregate_type=aggregate_type,
        aggregate_id=aggregate_id, payload_hash=payload_hash, status="pending",
        attempt_count=0, available_at=now or datetime.now(timezone.utc),
    )
    session.add(event)
    session.flush()
    return event


def process_outbox_event(session: Session, event: OutboxEvent, handler, now: datetime) -> OutboxEvent:
    if event.status == "processed" or event.available_at > now:
        return event
    event.status = "processing"
    event.attempt_count += 1
    try:
        handler(event)
        event.status = "processed"
        event.processed_at = now
    except Exception:
        event.status = "failed"
        event.available_at = now + timedelta(seconds=min(3600, 2 ** event.attempt_count * 60))
    return event

def emit_project_event(
    session: Session,
    project: Project,
    *,
    event_type: str,
    title: str,
    body: str,
    severity: str = "info",
    action_url: str | None = None,
    actor_user_id: uuid.UUID | None = None,
    aggregate_type: str,
    aggregate_id: uuid.UUID,
) -> OutboxEvent:
    payload = {"title": sanitize_sensitive(title), "body": sanitize_sensitive(body), "severity": severity, "action_url": action_url}
    event = enqueue_outbox_event(
        session, organization_id=project.organization_id, event_type=event_type,
        aggregate_type=aggregate_type, aggregate_id=aggregate_id, payload=payload,
    )
    recipients = {value for value in (actor_user_id, project.customer_user_id, project.project_manager_user_id) if value}
    recipients.update(session.scalars(select(ProjectMember.user_id).where(ProjectMember.project_id == project.id, ProjectMember.status == "active")).all())
    for user_id in recipients:
        key = f"{event_type}:{aggregate_type}:{aggregate_id}"
        exists = session.scalar(select(Notification.id).where(
            Notification.organization_id == project.organization_id,
            Notification.user_id == user_id,
            Notification.deduplication_key == key,
        ))
        if exists is None:
            create_notification(
                session, organization_id=project.organization_id, user_id=user_id, project_id=project.id,
                event_type=event_type, title=title, body=body, severity=severity,
                action_url=action_url, deduplication_key=key,
            )
    event.status = "processed"
    event.processed_at = datetime.now(timezone.utc)
    return event


def resolve_document_template(session: Session, organization_id: uuid.UUID, document_type: str, locale: str = "ja") -> DocumentTemplate:
    template = session.scalar(select(DocumentTemplate).where(
        DocumentTemplate.organization_id == organization_id,
        DocumentTemplate.document_type == document_type,
        DocumentTemplate.locale == locale,
        DocumentTemplate.status == "approved",
    ).order_by(DocumentTemplate.version_number.desc()))
    if template is None:
        template = session.scalar(select(DocumentTemplate).where(
            DocumentTemplate.organization_id.is_(None),
            DocumentTemplate.document_type == document_type,
            DocumentTemplate.locale == locale,
            DocumentTemplate.status == "approved",
        ).order_by(DocumentTemplate.version_number.desc()))
    if template is None:
        raise AppError("TEMPLATE_NOT_FOUND", "Document template not found")
    return template


def validate_document_payload(schema: dict, payload: dict) -> None:
    if schema.get("type") != "object" or not isinstance(payload, dict):
        raise AppError("INVALID_TEMPLATE_DATA", "Document payload does not match schema")
    properties = schema.get("properties", {})
    required = set(schema.get("required", []))
    if not isinstance(properties, dict) or required - set(payload):
        raise AppError("INVALID_TEMPLATE_DATA", "Required document fields are missing")
    if schema.get("additionalProperties", False) is False and set(payload) - set(properties):
        raise AppError("INVALID_TEMPLATE_DATA", "Unknown document fields are forbidden")
    expected_types = {"string": str, "integer": int, "number": (int, Decimal), "boolean": bool, "array": list, "object": dict}
    for key, value in payload.items():
        definition = properties.get(key, {})
        expected = expected_types.get(definition.get("type"))
        if expected is not None and not isinstance(value, expected):
            raise AppError("INVALID_TEMPLATE_DATA", "Document field type is invalid")
        if isinstance(value, str) and EXTERNAL_REFERENCE_PATTERN.search(value):
            raise AppError("INVALID_TEMPLATE_DATA", "External document references are forbidden")
