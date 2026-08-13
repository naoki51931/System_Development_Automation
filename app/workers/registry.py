from dataclasses import dataclass, field
import os
from pathlib import Path
import tempfile
from typing import Protocol

from sqlalchemy.orm import Session

from app.models.communications import OutboxEvent
from app.services.ai_providers import MockAIProvider
from app.services.communication_providers import (
    MockEmailProvider,
    MockNotificationProvider,
)
from app.services.storage import LocalArtifactStorage
from app.workers.exceptions import UnknownJobType


@dataclass
class WorkerContext:
    session: Session
    worker_id: str
    storage: LocalArtifactStorage = field(
        default_factory=lambda: LocalArtifactStorage(
            Path(
                os.getenv(
                    "APP_ARTIFACT_STORAGE_ROOT",
                    str(Path(tempfile.gettempdir()) / "systemnavigator-artifacts"),
                )
            )
        )
    )
    notification_provider: MockNotificationProvider = field(
        default_factory=MockNotificationProvider
    )
    email_provider: MockEmailProvider = field(default_factory=MockEmailProvider)
    ai_provider: MockAIProvider = field(default_factory=MockAIProvider)


class Handler(Protocol):
    def execute(self, job: OutboxEvent, context: WorkerContext) -> None: ...


class Registry:
    def __init__(self):
        self._handlers: dict[str, Handler] = {}

    def register(self, job_type: str, handler: Handler) -> None:
        self._handlers[job_type] = handler

    def get(self, job_type: str) -> Handler:
        try:
            return self._handlers[job_type]
        except KeyError as exc:
            raise UnknownJobType(f"Unregistered job type: {job_type[:100]}") from exc


def default_registry() -> Registry:
    from app.workers.documents import DocumentHandler
    from app.workers.maintenance import MaintenanceHandler
    from app.workers.notifications import EmailHandler, NotificationHandler
    from app.workers.outbox_handler import OutboxHandler
    from app.workers.workflows import WorkflowHandler

    registry = Registry()
    registry.register("outbox", OutboxHandler(registry))
    registry.register("notification", NotificationHandler())
    registry.register("email", EmailHandler())
    registry.register("document", DocumentHandler())
    registry.register("ai_workflow", WorkflowHandler())
    registry.register("maintenance", MaintenanceHandler())
    registry.register("estimate_expiration", MaintenanceHandler())
    registry.register("notification_expiration", MaintenanceHandler())
    return registry


def resolve_job_type(job: OutboxEvent) -> str:
    if job.event_type in {
        "outbox",
        "notification",
        "email",
        "document",
        "ai_workflow",
        "maintenance",
        "estimate_expiration",
        "notification_expiration",
    }:
        return job.event_type
    if job.aggregate_type in {"notification", "notification_delivery"}:
        return "notification"
    if job.aggregate_type == "email_message":
        return "email"
    if job.aggregate_type in {"document_generation_job", "document"}:
        return "document"
    if job.aggregate_type in {"workflow_job", "artifact_revision"}:
        return "ai_workflow"
    if job.aggregate_type == "maintenance_contract":
        return "maintenance"
    # Domain events are outbox fan-out work even when their event names vary.
    if job.aggregate_type in {
        "project",
        "artifact",
        "estimate",
        "contract",
        "payment",
        "change_request",
        "chat_message",
    }:
        return "outbox"
    return job.event_type
