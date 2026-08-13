from app.models.communications import OutboxEvent
from app.workers.exceptions import TenantMismatch
from app.workers.registry import Registry, WorkerContext, resolve_job_type


class OutboxHandler:
    def __init__(self, registry: Registry):
        self.registry = registry

    def execute(self, job: OutboxEvent, context: WorkerContext) -> None:
        # Domain events created by emit_project_event already fan out notifications.
        # Reaching this handler means the durable event itself is the idempotency record.
        if job.organization_id is None:
            raise TenantMismatch("Outbox event has no organization")
        target = resolve_job_type(job)
        if target != "outbox":
            self.registry.get(target).execute(job, context)
