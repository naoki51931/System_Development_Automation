"""Idempotent local Mock-AI workflow completion checks."""

from app.models.automation import WorkflowJob
from app.models.communications import OutboxEvent
from app.workers.exceptions import NonRetryableWorkerError, TenantMismatch
from app.workers.registry import WorkerContext


class WorkflowHandler:
    def execute(self, job: OutboxEvent, context: WorkerContext) -> None:
        workflow = context.session.get(WorkflowJob, job.aggregate_id)
        if workflow is None:
            raise NonRetryableWorkerError("Workflow job not found")
        if workflow.organization_id != job.organization_id:
            raise TenantMismatch("Workflow organization mismatch")
        if workflow.status in {"completed", "escalated"}:
            return
        if workflow.attempt_count >= workflow.max_attempts:
            workflow.status = "escalated"
            workflow.last_error_code = "AI_RETRY_LIMIT_REACHED"
            return
        # run_auto_revision owns version creation, review, AI-run and cost atomically.
        # Legacy running rows lack the setting/access snapshot needed to recreate it;
        # fail safely instead of fabricating a second version or billing entry.
        workflow.status = "failed"
        workflow.last_error_code = "WORKFLOW_RESUME_CONTEXT_MISSING"
        raise NonRetryableWorkerError("Workflow resume context is unavailable")
