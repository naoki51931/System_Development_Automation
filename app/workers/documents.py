"""Safe, snapshot-only document recovery using deterministic artifacts."""

import hashlib
import html
import uuid
from datetime import datetime, timezone

from app.models.communications import DocumentGenerationJob, OutboxEvent
from app.models.project import Artifact, ArtifactVersion
from app.services.communications import generate_local_pdf
from app.workers.exceptions import NonRetryableWorkerError, TenantMismatch
from app.workers.registry import WorkerContext
from app.workers.snapshots import assert_tenant, complete_step, load_snapshot, step


class DocumentHandler:
    STEPS = (
        "snapshot_created",
        "artifact_version_reserved",
        "rendering",
        "rendered",
        "stored",
        "verified",
        "database_committed",
        "completed",
    )

    def execute(self, job: OutboxEvent, context: WorkerContext) -> None:
        generation = context.session.get(DocumentGenerationJob, job.aggregate_id)
        if generation is None:
            raise NonRetryableWorkerError("Document generation job not found")
        if generation.organization_id != job.organization_id:
            raise TenantMismatch("Document organization mismatch")
        snapshot = load_snapshot(context.session, document_job_id=generation.id)
        if snapshot is None:
            generation.status = "failed"
            generation.failure_code = "RESUME_SNAPSHOT_MISSING"
            generation.resume_block_reason = "immutable_snapshot_missing"
            generation.resume_blocked_at = datetime.now(timezone.utc)
            return
        assert_tenant(snapshot, job.organization_id)
        payload = snapshot.input_payload
        target_id = uuid.UUID(payload["deterministic_artifact_version_id"])
        artifact_id = uuid.UUID(payload["artifact_id"])

        complete_step(step(context.session, snapshot, "snapshot_created"))
        artifact = context.session.get(Artifact, artifact_id)
        if artifact is None:
            artifact = Artifact(
                id=artifact_id,
                organization_id=generation.organization_id,
                project_id=generation.project_id,
                artifact_type=payload["artifact_type"],
                title=payload["artifact_title"],
                status="draft",
                created_by_user_id=snapshot.actor_user_id,
            )
            context.session.add(artifact)
            context.session.flush()
        elif artifact.organization_id != generation.organization_id:
            raise TenantMismatch("Artifact organization mismatch")
        complete_step(
            step(context.session, snapshot, "artifact_version_reserved"),
            result_reference=str(target_id),
        )

        existing = context.session.get(ArtifactVersion, target_id)
        if existing:
            try:
                metadata = context.storage.head_object(existing.storage_key)
            except Exception as exc:
                raise NonRetryableWorkerError(
                    "Document DB record has no stored file"
                ) from exc
            if metadata.content_hash != existing.content_hash:
                raise NonRetryableWorkerError("Stored document hash mismatch")
            self._finish(context, generation, artifact, existing, snapshot)
            return

        render_step = step(context.session, snapshot, "rendering")
        render_step.attempt_count += 1
        render_step.status = "running"
        text = payload["rendered_text"]
        output_format = payload["output_format"]
        content = (
            generate_local_pdf(text)
            if output_format == "pdf"
            else f"<html><body><pre>{html.escape(text)}</pre></body></html>".encode()
            if output_format == "html"
            else text.encode()
        )
        rendered_hash = hashlib.sha256(content).hexdigest()
        complete_step(render_step, result_hash=rendered_hash)
        complete_step(
            step(context.session, snapshot, "rendered"), result_hash=rendered_hash
        )

        storage_key = payload["storage_key"]
        try:
            metadata = context.storage.head_object(storage_key)
            if metadata.content_hash != rendered_hash:
                raise NonRetryableWorkerError("Existing document object hash mismatch")
        except NonRetryableWorkerError:
            raise
        except Exception:
            metadata = context.storage.put_object(
                storage_key, content, payload["mime_type"]
            )
        complete_step(
            step(context.session, snapshot, "stored"),
            result_reference=storage_key,
            result_hash=metadata.content_hash,
        )
        verified = context.storage.head_object(storage_key)
        if verified.content_hash != rendered_hash:
            raise NonRetryableWorkerError("Document verification hash mismatch")
        complete_step(
            step(context.session, snapshot, "verified"),
            result_hash=verified.content_hash,
        )

        version = ArtifactVersion(
            id=target_id,
            artifact_id=artifact.id,
            version_number=payload["target_version_number"],
            storage_key=storage_key,
            content_hash=verified.content_hash,
            mime_type=verified.mime_type,
            file_size=verified.size,
            generated_by="human",
            created_by_user_id=snapshot.actor_user_id,
            change_summary="Resumable local document generation",
        )
        context.session.add(version)
        context.session.flush()
        complete_step(
            step(context.session, snapshot, "database_committed"),
            result_reference=str(version.id),
            result_hash=version.content_hash,
        )
        self._finish(context, generation, artifact, version, snapshot)

    @staticmethod
    def _finish(context, generation, artifact, version, snapshot):
        artifact.current_version_id = version.id
        generation.artifact_id = artifact.id
        generation.artifact_version_id = version.id
        generation.storage_key = version.storage_key
        generation.content_hash = version.content_hash
        generation.file_size = version.file_size
        generation.status = "completed"
        generation.completed_at = datetime.now(timezone.utc)
        generation.failure_code = None
        generation.resume_block_reason = None
        complete_step(
            step(context.session, snapshot, "completed"),
            result_reference=str(version.id),
            result_hash=version.content_hash,
        )
