import hashlib
import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.automation import WorkflowJobInput, WorkflowJobStep
from app.workers.exceptions import NonRetryableWorkerError, TenantMismatch

SCHEMA_VERSION = "1"
DOCUMENT_KEYS = frozenset(
    {
        "document_type",
        "source_revision",
        "output_format",
        "locale",
        "artifact_id",
        "artifact_type",
        "artifact_title",
        "target_version_number",
        "deterministic_artifact_version_id",
        "storage_key",
        "requested_by_user_id",
        "rendered_text",
        "mime_type",
    }
)
AI_KEYS = frozenset(
    {
        "source_artifact_version_id",
        "source_content_hash",
        "review_id",
        "unresolved_comment_ids",
        "comment_set_hash",
        "provider",
        "model",
        "operation_type",
        "prompt_version",
        "settings_id",
        "settings_version",
        "review_threshold",
        "max_auto_revision_count",
        "current_revision_attempt",
        "minute_rate_snapshot",
        "input_rate_snapshot",
        "output_rate_snapshot",
        "target_artifact_id",
        "target_version_number",
        "deterministic_target_version_id",
        "ai_run_id",
        "ai_run_idempotency_key",
        "billing_idempotency_key",
        "requested_by_user_id",
        "mime_type",
        "storage_key",
    }
)
FORBIDDEN_FRAGMENTS = (
    "api_key",
    "authorization",
    "jwt",
    "password",
    "database_url",
    "card",
    "cvc",
)


def canonical_hash(value) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def deterministic_uuid(key: str, purpose: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"systemnavigator:{purpose}:{key}")


def validate_payload(input_type: str, payload: dict) -> None:
    allowed = DOCUMENT_KEYS if input_type == "document" else AI_KEYS
    if set(payload) - allowed:
        raise NonRetryableWorkerError("Snapshot contains unsupported keys")
    encoded = json.dumps(payload, default=str).lower()
    if any(fragment in encoded for fragment in FORBIDDEN_FRAGMENTS):
        raise NonRetryableWorkerError("Snapshot contains forbidden secret fields")


def create_snapshot(
    session: Session,
    *,
    input_type: str,
    organization_id,
    project_id,
    actor_user_id,
    source_reference_type: str,
    source_reference_id,
    payload: dict,
    access_context: dict,
    settings_snapshot: dict | None = None,
    template_snapshot: dict | None = None,
    workflow_job_id=None,
    document_job_id=None,
) -> WorkflowJobInput:
    validate_payload(input_type, payload)
    payload_hash = canonical_hash(payload)
    identity = {
        "organization_id": organization_id,
        "project_id": project_id,
        "input_type": input_type,
        "source_reference_type": source_reference_type,
        "source_reference_id": source_reference_id,
        "payload_hash": payload_hash,
        "settings": settings_snapshot or {},
        "template": template_snapshot or {},
    }
    key = canonical_hash(identity)
    existing = session.scalar(
        select(WorkflowJobInput).where(WorkflowJobInput.idempotency_key == key)
    )
    if existing:
        return existing
    snapshot = WorkflowJobInput(
        id=deterministic_uuid(key, "snapshot"),
        organization_id=organization_id,
        project_id=project_id,
        workflow_job_id=workflow_job_id,
        document_job_id=document_job_id,
        input_type=input_type,
        schema_version=SCHEMA_VERSION,
        source_reference_type=source_reference_type,
        source_reference_id=source_reference_id,
        actor_user_id=actor_user_id,
        access_context_hash=canonical_hash(access_context),
        settings_snapshot=settings_snapshot or {},
        template_snapshot=template_snapshot or {},
        input_payload=payload,
        input_payload_hash=payload_hash,
        idempotency_key=key,
    )
    session.add(snapshot)
    session.flush()
    return snapshot


def load_snapshot(session: Session, *, document_job_id=None, workflow_job_id=None):
    query = select(WorkflowJobInput)
    query = query.where(
        WorkflowJobInput.document_job_id == document_job_id
        if document_job_id is not None
        else WorkflowJobInput.workflow_job_id == workflow_job_id
    )
    snapshot = session.scalar(query)
    if snapshot is None:
        return None
    if snapshot.schema_version != SCHEMA_VERSION:
        raise NonRetryableWorkerError("Unsupported snapshot schema version")
    validate_payload(snapshot.input_type, snapshot.input_payload)
    if canonical_hash(snapshot.input_payload) != snapshot.input_payload_hash:
        raise NonRetryableWorkerError("Snapshot payload hash mismatch")
    return snapshot


def step(session: Session, snapshot: WorkflowJobInput, name: str) -> WorkflowJobStep:
    existing = session.scalar(
        select(WorkflowJobStep).where(
            WorkflowJobStep.workflow_input_id == snapshot.id,
            WorkflowJobStep.step_name == name,
        )
    )
    if existing:
        return existing
    value = WorkflowJobStep(
        id=deterministic_uuid(snapshot.idempotency_key, f"step:{name}"),
        workflow_input_id=snapshot.id,
        step_name=name,
        status="pending",
        idempotency_key=canonical_hash(
            {"snapshot": snapshot.idempotency_key, "step": name}
        ),
        attempt_count=0,
    )
    session.add(value)
    session.flush()
    return value


def complete_step(
    value: WorkflowJobStep,
    *,
    result_reference: str | None = None,
    result_hash: str | None = None,
) -> None:
    if value.status == "completed":
        return
    now = datetime.now(timezone.utc)
    value.status = "completed"
    value.started_at = value.started_at or now
    value.completed_at = now
    value.attempt_count += 1
    value.result_reference = result_reference
    value.result_hash = result_hash


def assert_tenant(snapshot: WorkflowJobInput, organization_id) -> None:
    if snapshot.organization_id != organization_id:
        raise TenantMismatch("Snapshot organization mismatch")
