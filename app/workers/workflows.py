"""Snapshot-only Mock-AI workflow resume with deterministic billing and versions."""

import hashlib
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from app.models.automation import WorkflowJob
from app.models.communications import OutboxEvent
from app.models.project import AIRun, Artifact, ArtifactVersion, Review, ReviewComment
from app.services.automation import ResolvedAISetting, apply_ai_cost
from app.workers.exceptions import NonRetryableWorkerError, TenantMismatch
from app.workers.registry import WorkerContext
from app.workers.snapshots import (
    assert_tenant,
    complete_step,
    deterministic_uuid,
    load_snapshot,
    step,
)


class WorkflowHandler:
    STEPS = (
        "snapshot_created",
        "ai_run_reserved",
        "revision_generated",
        "artifact_version_reserved",
        "content_stored",
        "review_generated",
        "cost_calculated",
        "workflow_state_updated",
        "completed",
    )

    def execute(self, job: OutboxEvent, context: WorkerContext) -> None:
        workflow = context.session.get(WorkflowJob, job.aggregate_id)
        if workflow is None:
            raise NonRetryableWorkerError("Workflow job not found")
        if workflow.organization_id != job.organization_id:
            raise TenantMismatch("Workflow organization mismatch")
        if workflow.status in {"completed", "escalated"}:
            return
        snapshot = load_snapshot(context.session, workflow_job_id=workflow.id)
        if snapshot is None:
            workflow.status = "failed"
            workflow.last_error_code = "RESUME_SNAPSHOT_MISSING"
            workflow.resume_block_reason = "immutable_snapshot_missing"
            workflow.resume_blocked_at = datetime.now(timezone.utc)
            return
        assert_tenant(snapshot, job.organization_id)
        payload = snapshot.input_payload
        source = context.session.get(
            ArtifactVersion, uuid.UUID(payload["source_artifact_version_id"])
        )
        artifact = context.session.get(
            Artifact, uuid.UUID(payload["target_artifact_id"])
        )
        if source is None or artifact is None:
            raise NonRetryableWorkerError("Workflow source is missing")
        if artifact.organization_id != workflow.organization_id:
            raise TenantMismatch("Workflow artifact organization mismatch")
        source_content = context.storage.get_object(source.storage_key)
        if hashlib.sha256(source_content).hexdigest() != payload["source_content_hash"]:
            raise NonRetryableWorkerError("Workflow source hash mismatch")
        comment_ids = payload["unresolved_comment_ids"]
        comments = [
            context.session.get(ReviewComment, uuid.UUID(value))
            for value in comment_ids
        ]
        if any(value is None for value in comments):
            raise NonRetryableWorkerError("Workflow comment snapshot is incomplete")
        comment_identity = [
            {
                "id": str(value.id),
                "body_hash": hashlib.sha256(value.body.encode()).hexdigest(),
            }
            for value in comments
        ]
        from app.workers.snapshots import canonical_hash

        if canonical_hash(comment_identity) != payload["comment_set_hash"]:
            raise NonRetryableWorkerError("Workflow comment set hash mismatch")

        complete_step(step(context.session, snapshot, "snapshot_created"))
        ai_run_id = uuid.UUID(payload["ai_run_id"])
        ai_run = context.session.get(AIRun, ai_run_id)
        if ai_run is None:
            ai_run = AIRun(
                id=ai_run_id,
                organization_id=workflow.organization_id,
                project_id=workflow.project_id,
                provider=payload["provider"],
                model=payload["model"],
                operation_type=payload["operation_type"],
                status="running",
                request_hash=snapshot.input_payload_hash,
                prompt_version=payload["prompt_version"],
                retry_count=payload["current_revision_attempt"] - 1,
                started_at=datetime.now(timezone.utc),
            )
            context.session.add(ai_run)
            context.session.flush()
        complete_step(
            step(context.session, snapshot, "ai_run_reserved"),
            result_reference=str(ai_run.id),
        )

        target_id = uuid.UUID(payload["deterministic_target_version_id"])
        version = context.session.get(ArtifactVersion, target_id)
        if version is None:
            revised = context.ai_provider.revise(
                source_content, [value.body for value in comments]
            )
            revised_hash = hashlib.sha256(revised.content).hexdigest()
            complete_step(
                step(context.session, snapshot, "revision_generated"),
                result_hash=revised_hash,
            )
            complete_step(
                step(context.session, snapshot, "artifact_version_reserved"),
                result_reference=str(target_id),
            )
            storage_key = payload["storage_key"]
            try:
                metadata = context.storage.head_object(storage_key)
                if metadata.content_hash != revised_hash:
                    raise NonRetryableWorkerError(
                        "Workflow stored result hash mismatch"
                    )
            except NonRetryableWorkerError:
                raise
            except Exception:
                metadata = context.storage.put_object(
                    storage_key, revised.content, payload["mime_type"]
                )
            complete_step(
                step(context.session, snapshot, "content_stored"),
                result_reference=storage_key,
                result_hash=metadata.content_hash,
            )
            version = ArtifactVersion(
                id=target_id,
                artifact_id=artifact.id,
                version_number=payload["target_version_number"],
                storage_key=storage_key,
                content_hash=metadata.content_hash,
                mime_type=metadata.mime_type,
                file_size=metadata.size,
                generated_by="ai",
                ai_run_id=ai_run.id,
                change_summary="Resumable Mock AI revision",
            )
            context.session.add(version)
            context.session.flush()
            reviewed = context.ai_provider.review(revised.content)
            review_id = deterministic_uuid(snapshot.idempotency_key, "review")
            review = context.session.get(Review, review_id)
            if review is None:
                review = Review(
                    id=review_id,
                    organization_id=workflow.organization_id,
                    project_id=workflow.project_id,
                    artifact_version_id=version.id,
                    review_type="ai",
                    ai_run_id=ai_run.id,
                    status="passed"
                    if (reviewed.score or 0) >= payload["review_threshold"]
                    else "failed",
                    score=reviewed.score,
                    started_at=datetime.now(timezone.utc),
                    completed_at=datetime.now(timezone.utc),
                )
                context.session.add(review)
            ai_run.input_tokens = revised.input_tokens + reviewed.input_tokens
            ai_run.output_tokens = revised.output_tokens + reviewed.output_tokens
            ai_run.duration_ms = revised.duration_ms + reviewed.duration_ms
            ai_run.status = "completed"
            ai_run.completed_at = datetime.now(timezone.utc)
        else:
            metadata = context.storage.head_object(version.storage_key)
            if metadata.content_hash != version.content_hash:
                raise NonRetryableWorkerError("Workflow version storage hash mismatch")
            review = context.session.get(
                Review, deterministic_uuid(snapshot.idempotency_key, "review")
            )
            if review is None:
                raise NonRetryableWorkerError("Workflow version has no review")
        complete_step(
            step(context.session, snapshot, "review_generated"),
            result_reference=str(review.id),
        )

        if step(context.session, snapshot, "cost_calculated").status != "completed":
            setting = ResolvedAISetting(
                provider=payload["provider"],
                model=payload["model"],
                operation_type=payload["operation_type"],
                review_threshold=payload["review_threshold"],
                max_auto_revision_count=payload["max_auto_revision_count"],
                minute_rate=Decimal(payload["minute_rate_snapshot"]),
                token_input_rate=Decimal(payload["input_rate_snapshot"]),
                token_output_rate=Decimal(payload["output_rate_snapshot"]),
                currency=snapshot.settings_snapshot["currency"],
            )
            apply_ai_cost(ai_run, setting)
            complete_step(
                step(context.session, snapshot, "cost_calculated"),
                result_hash=payload["billing_idempotency_key"],
            )
        artifact.current_version_id = version.id
        if review.status == "passed":
            artifact.status = "human_reviewing"
            workflow.status = "completed"
        elif payload["current_revision_attempt"] >= payload["max_auto_revision_count"]:
            artifact.status = "revision_requested"
            workflow.status = "escalated"
            workflow.last_error_code = "AI_RETRY_LIMIT_REACHED"
        else:
            artifact.status = "revision_requested"
            workflow.status = "failed"
            workflow.last_error_code = "AI_REVIEW_THRESHOLD_NOT_MET"
        complete_step(
            step(context.session, snapshot, "workflow_state_updated"),
            result_reference=workflow.status,
        )
        complete_step(
            step(context.session, snapshot, "completed"),
            result_reference=str(version.id),
            result_hash=version.content_hash,
        )
