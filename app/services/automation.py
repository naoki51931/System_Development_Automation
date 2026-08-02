import hashlib
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from app.audit import record_audit_log
from app.auth.dependencies import OrganizationAccess, ensure_resource_organization
from app.errors import AppError
from app.models.automation import AISetting, ArtifactUploadIntent, WorkflowJob
from app.models.project import AIRun, Artifact, ArtifactVersion, Review, ReviewComment
from app.services.ai_providers import AIProvider
from app.services.storage import ALLOWED_MIME_TYPES, DEFAULT_MAX_FILE_SIZE, ArtifactStorage
from app.services.workflow import ARTIFACT_WRITE_ROLES, REVIEW_ROLES, create_ai_run, create_review, move_to_human_review

ZERO = Decimal("0.00000000")


@dataclass(frozen=True)
class ResolvedAISetting:
    provider: str
    model: str
    operation_type: str
    enabled: bool = True
    review_threshold: int = 95
    max_auto_revision_count: int = 3
    minute_rate: Decimal = ZERO
    token_input_rate: Decimal = ZERO
    token_output_rate: Decimal = ZERO
    currency: str = "JPY"
    source: str = "system"
    version: int | None = None


def resolve_ai_setting(session: Session, organization_id: uuid.UUID, project_id: uuid.UUID | None, provider: str, model: str, operation_type: str) -> ResolvedAISetting:
    conditions = [
        AISetting.organization_id == organization_id, AISetting.provider == provider,
        AISetting.model == model, AISetting.operation_type == operation_type,
    ]
    setting = None
    if project_id is not None:
        setting = session.scalar(select(AISetting).where(*conditions, AISetting.project_id == project_id))
    source = "project"
    if setting is None:
        setting = session.scalar(select(AISetting).where(*conditions, AISetting.project_id.is_(None)))
        source = "organization"
    if setting is None:
        return ResolvedAISetting(provider, model, operation_type)
    return ResolvedAISetting(
        setting.provider, setting.model, setting.operation_type, setting.enabled,
        setting.review_threshold, setting.max_auto_revision_count, setting.minute_rate,
        setting.token_input_rate, setting.token_output_rate, setting.currency, source, setting.version,
    )


def calculate_ai_cost(duration_ms: int, input_tokens: int, output_tokens: int, minute_rate: Decimal, input_rate: Decimal, output_rate: Decimal) -> tuple[int, Decimal]:
    if min(duration_ms, input_tokens, output_tokens) < 0:
        raise AppError("INVALID_REQUEST", "AI usage values cannot be negative")
    billed_minutes = (duration_ms + 59999) // 60000 if duration_ms else 0
    cost = Decimal(billed_minutes) * minute_rate + Decimal(input_tokens) * input_rate + Decimal(output_tokens) * output_rate
    return billed_minutes, cost.quantize(Decimal("0.00000001"))


def apply_ai_cost(run: AIRun, setting: ResolvedAISetting) -> Decimal:
    minutes, cost = calculate_ai_cost(run.duration_ms or 0, run.input_tokens or 0, run.output_tokens or 0, setting.minute_rate, setting.token_input_rate, setting.token_output_rate)
    run.billed_minutes = minutes
    run.minute_rate_snapshot = setting.minute_rate
    run.input_rate_snapshot = setting.token_input_rate
    run.output_rate_snapshot = setting.token_output_rate
    run.calculated_cost = cost
    run.estimated_cost = cost
    return cost


def check_expected_version(resource, expected_version: int) -> None:
    if resource.version != expected_version:
        raise AppError("VERSION_CONFLICT", "Resource was updated by another request")


def flush_versioned(session: Session) -> None:
    try:
        session.flush()
    except StaleDataError as exc:
        raise AppError("VERSION_CONFLICT", "Resource was updated by another request") from exc


def update_ai_setting(session: Session, setting: AISetting, expected_version: int, values: dict) -> AISetting:
    check_expected_version(setting, expected_version)
    for key, value in values.items():
        if key not in {"enabled", "review_threshold", "max_auto_revision_count", "minute_rate", "token_input_rate", "token_output_rate", "currency"}:
            raise AppError("INVALID_REQUEST", "Unsupported setting field")
        setattr(setting, key, value)
    flush_versioned(session)
    return setting


def create_upload_intent(session: Session, storage: ArtifactStorage, artifact: Artifact, access: OrganizationAccess, *, filename: str, mime_type: str, file_size: int, content_hash: str, expires_seconds: int = 900) -> tuple[ArtifactUploadIntent, str]:
    ensure_resource_organization(access, artifact.organization_id)
    if access.role_codes.isdisjoint(ARTIFACT_WRITE_ROLES):
        raise AppError("PERMISSION_DENIED", "Permission denied")
    if mime_type not in ALLOWED_MIME_TYPES:
        raise AppError("UNSUPPORTED_MEDIA_TYPE", "Unsupported media type")
    if file_size > DEFAULT_MAX_FILE_SIZE:
        raise AppError("FILE_TOO_LARGE", "File exceeds configured size limit")
    version_id = uuid.uuid4()
    key = storage.build_storage_key(artifact.organization_id, artifact.project_id, artifact.id, version_id, filename)  # type: ignore[attr-defined]
    if len(content_hash) != 64 or any(c not in "0123456789abcdef" for c in content_hash.lower()):
        raise AppError("INVALID_REQUEST", "Expected SHA-256 hash is invalid")
    intent = ArtifactUploadIntent(
        version_id=version_id, organization_id=artifact.organization_id, project_id=artifact.project_id,
        artifact_id=artifact.id, storage_key=key, mime_type=mime_type, expected_size=file_size,
        expected_hash=content_hash.lower(), created_by_user_id=access.user.id,
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=expires_seconds), status="pending",
    )
    session.add(intent)
    session.flush()
    return intent, storage.create_upload_url(key, expires_seconds)


def complete_upload(session: Session, storage: ArtifactStorage, intent: ArtifactUploadIntent, artifact: Artifact, access: OrganizationAccess) -> ArtifactVersion:
    ensure_resource_organization(access, intent.organization_id)
    if artifact.id != intent.artifact_id or artifact.organization_id != intent.organization_id:
        raise AppError("PERMISSION_DENIED", "Artifact does not match upload intent")
    if intent.status != "pending" or intent.expires_at < datetime.now(timezone.utc):
        raise AppError("INVALID_STATE_TRANSITION", "Upload intent is not active")
    metadata = storage.head_object(intent.storage_key)
    if metadata.mime_type != intent.mime_type:
        raise AppError("UNSUPPORTED_MEDIA_TYPE", "Uploaded MIME type does not match")
    if metadata.size != intent.expected_size:
        raise AppError("INVALID_REQUEST", "Uploaded file size does not match")
    if metadata.content_hash != intent.expected_hash:
        raise AppError("HASH_MISMATCH", "Uploaded file hash does not match")
    next_number = (session.scalar(select(func.max(ArtifactVersion.version_number)).where(ArtifactVersion.artifact_id == artifact.id)) or 0) + 1
    version = ArtifactVersion(
        id=intent.version_id, artifact_id=artifact.id, version_number=next_number,
        storage_key=intent.storage_key, content_hash=metadata.content_hash, mime_type=metadata.mime_type,
        file_size=metadata.size, generated_by="human", created_by_user_id=access.user.id,
    )
    session.add(version)
    session.flush()
    artifact.current_version_id = version.id
    intent.status = "completed"
    return version


def transition_comment(session: Session, comment: ReviewComment, review: Review, access: OrganizationAccess, action: str, request_id: uuid.UUID, expected_version: int) -> ReviewComment:
    ensure_resource_organization(access, review.organization_id)
    if access.role_codes.isdisjoint(REVIEW_ROLES):
        raise AppError("PERMISSION_DENIED", "Permission denied")
    check_expected_version(review, expected_version)
    allowed = {("open", "accepted"), ("open", "rejected"), ("accepted", "resolved"), ("open", "resolved")}
    if (comment.status, action) not in allowed:
        raise AppError("INVALID_STATE_TRANSITION", "Comment state transition is not allowed")
    before = comment.status
    comment.status = action
    review.version += 1
    if action == "resolved":
        comment.resolved_at = datetime.now(timezone.utc)
        comment.resolved_by_user_id = access.user.id
    record_audit_log(
        session, organization_id=review.organization_id, actor_user_id=access.user.id,
        action=f"review_comment.{action}", resource_type="review_comment", resource_id=comment.id,
        request_id=request_id, before={"status": before}, after={"status": action},
    )
    flush_versioned(session)
    return comment


def run_auto_revision(session: Session, storage: ArtifactStorage, provider: AIProvider, artifact: Artifact, access: OrganizationAccess, setting: ResolvedAISetting) -> WorkflowJob:
    ensure_resource_organization(access, artifact.organization_id)
    job = WorkflowJob(
        organization_id=artifact.organization_id, project_id=artifact.project_id,
        job_type="auto_revision", status="running", attempt_count=0,
        max_attempts=setting.max_auto_revision_count, locked_at=datetime.now(timezone.utc), locked_by="local-worker",
    )
    session.add(job)
    session.flush()
    current = session.get(ArtifactVersion, artifact.current_version_id)
    if current is None or artifact.status != "revision_requested":
        raise AppError("INVALID_STATE_TRANSITION", "Artifact is not awaiting revision")
    comments = session.scalars(
        select(ReviewComment).join(Review).where(
            Review.artifact_version_id == current.id,
            ReviewComment.status.in_(["open", "accepted"]),
        )
    ).all()
    comment_bodies = [comment.body for comment in comments]
    content = storage.get_object(current.storage_key)
    for attempt in range(1, job.max_attempts + 1):
        job.attempt_count = attempt
        revised = provider.revise(content, comment_bodies)
        reviewed = provider.review(revised.content)
        run = create_ai_run(
            session, organization_id=artifact.organization_id, project_id=artifact.project_id,
            provider=setting.provider, model=setting.model, operation_type="revision", status="completed",
            input_tokens=revised.input_tokens + reviewed.input_tokens,
            output_tokens=revised.output_tokens + reviewed.output_tokens,
            duration_ms=revised.duration_ms + reviewed.duration_ms, retry_count=attempt - 1,
            request_hash=hashlib.sha256(content).hexdigest(), prompt_version="mock-auto-revision-v1",
        )
        apply_ai_cost(run, setting)
        version_id = uuid.uuid4()
        key = storage.build_storage_key(artifact.organization_id, artifact.project_id, artifact.id, version_id, f"auto-revision-{attempt}.md")  # type: ignore[attr-defined]
        metadata = storage.put_object(key, revised.content, current.mime_type)
        next_number = (session.scalar(select(func.max(ArtifactVersion.version_number)).where(ArtifactVersion.artifact_id == artifact.id)) or 0) + 1
        version = ArtifactVersion(
            id=version_id, artifact_id=artifact.id, version_number=next_number, storage_key=key,
            content_hash=metadata.content_hash, mime_type=metadata.mime_type, file_size=metadata.size,
            generated_by="ai", ai_run_id=run.id, change_summary="Mock AI automatic revision",
        )
        session.add(version)
        session.flush()
        artifact.current_version_id = version.id
        artifact.status = "ai_reviewing"
        create_review(session, version, access, passing_score=setting.review_threshold, review_type="ai", ai_run_id=run.id, status="passed" if (reviewed.score or 0) >= setting.review_threshold else "failed", score=reviewed.score)
        if (reviewed.score or 0) >= setting.review_threshold:
            move_to_human_review(session, artifact, version, passing_score=setting.review_threshold)
            job.status = "completed"
            return job
        content = revised.content
        artifact.status = "revision_requested"
    job.status = "escalated"
    job.last_error_code = "AI_RETRY_LIMIT_REACHED"
    return job
