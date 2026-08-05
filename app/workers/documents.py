"""Resume locally generated documents without publishing partial artifacts."""

from app.models.communications import DocumentGenerationJob, OutboxEvent
from app.models.project import ArtifactVersion
from app.workers.exceptions import NonRetryableWorkerError, TenantMismatch
from app.workers.registry import WorkerContext


class DocumentHandler:
    def execute(self, job: OutboxEvent, context: WorkerContext) -> None:
        generation = context.session.get(DocumentGenerationJob, job.aggregate_id)
        if generation is None:
            raise NonRetryableWorkerError("Document generation job not found")
        if generation.organization_id != job.organization_id:
            raise TenantMismatch("Document organization mismatch")
        if generation.status == "completed":
            version = context.session.get(
                ArtifactVersion, generation.artifact_version_id
            )
            if (
                version is None
                or context.storage.head_object(version.storage_key).content_hash
                != version.content_hash
            ):
                raise NonRetryableWorkerError("Completed document artifact is invalid")
            return
        # API generation is atomic: a failed transaction has no reusable DB artifact.
        # A persisted incomplete job is deliberately failed for a caller to enqueue
        # again with the same authoritative idempotency hash; it is never published.
        generation.attempt_count += 1
        generation.status = "failed"
        generation.failure_code = "DOCUMENT_RESUME_REQUIRED"
        generation.failure_message_sanitized = "Document generation must be resumed"
        raise RuntimeError("DOCUMENT_RESUME_REQUIRED")
