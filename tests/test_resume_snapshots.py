import hashlib
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import func, select

from app.models.automation import WorkflowJob, WorkflowJobStep
from app.models.communications import DocumentGenerationJob, OutboxEvent
from app.models.project import AIRun, Artifact, ArtifactVersion, Review, ReviewComment
from app.services.storage import LocalArtifactStorage
from app.workers.documents import DocumentHandler
from app.workers.registry import WorkerContext
from app.workers.snapshots import canonical_hash, create_snapshot, deterministic_uuid
from app.workers.workflows import WorkflowHandler
from tests.test_unmet_quality_gates import quality_context


def outbox_for(organization_id, aggregate_id, aggregate_type):
    return OutboxEvent(
        organization_id=organization_id,
        event_type="document"
        if aggregate_type == "document_generation_job"
        else "ai_workflow",
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        payload_hash="a" * 64,
        status="processing",
        available_at=datetime.now(timezone.utc),
    )


def document_snapshot(session, tmp_path):
    org, user, _access, project = quality_context(session)
    generation = DocumentGenerationJob(
        organization_id=org.id,
        project_id=project.id,
        document_type="basic_design",
        output_format="pdf",
        input_payload_hash="b" * 64,
        status="processing",
    )
    session.add(generation)
    session.flush()
    key = canonical_hash(
        {"job": str(generation.id), "source_revision": project.version}
    )
    artifact_id = deterministic_uuid(key, "document-artifact")
    version_id = deterministic_uuid(key, "document-version")
    storage = LocalArtifactStorage(tmp_path)
    storage_key = storage.build_storage_key(
        org.id, project.id, artifact_id, version_id, "basic-design.pdf"
    )
    generation.idempotency_key = key
    snapshot = create_snapshot(
        session,
        input_type="document",
        organization_id=org.id,
        project_id=project.id,
        actor_user_id=user.id,
        source_reference_type="project",
        source_reference_id=project.id,
        document_job_id=generation.id,
        access_context={
            "roles": ["project_manager"],
            "membership": str(_access.membership.id),
        },
        template_snapshot={
            "template_id": None,
            "version": 1,
            "schema_version": "1",
            "content_hash": hashlib.sha256(b"built-in-basic-design-v1").hexdigest(),
        },
        payload={
            "document_type": "basic_design",
            "source_revision": project.version,
            "output_format": "pdf",
            "locale": "ja",
            "artifact_id": str(artifact_id),
            "artifact_type": "basic_design",
            "artifact_title": "basic_design document",
            "target_version_number": 1,
            "deterministic_artifact_version_id": str(version_id),
            "storage_key": storage_key,
            "requested_by_user_id": str(user.id),
            "rendered_text": f"Project: {project.name}\nRevision: {project.version}",
            "mime_type": "application/pdf",
        },
    )
    return org, generation, snapshot, storage, version_id


def test_document_snapshot_resume_is_idempotent_and_immutable(db_session, tmp_path):
    org, generation, snapshot, storage, version_id = document_snapshot(
        db_session, tmp_path
    )
    handler = DocumentHandler()
    event = outbox_for(org.id, generation.id, "document_generation_job")
    context = WorkerContext(db_session, "resume-worker", storage=storage)
    handler.execute(event, context)
    db_session.flush()
    assert (
        generation.status == "completed"
        and generation.artifact_version_id == version_id
    )
    before_versions = db_session.scalar(
        select(func.count()).select_from(ArtifactVersion)
    )
    before_files = sorted(str(value) for value in tmp_path.rglob("*.pdf"))
    handler.execute(event, context)
    db_session.flush()
    assert (
        db_session.scalar(select(func.count()).select_from(ArtifactVersion))
        == before_versions
    )
    assert sorted(str(value) for value in tmp_path.rglob("*.pdf")) == before_files
    assert (
        len(
            db_session.scalars(
                select(WorkflowJobStep).where(
                    WorkflowJobStep.workflow_input_id == snapshot.id
                )
            ).all()
        )
        == 8
    )

    savepoint = db_session.begin_nested()
    snapshot.input_payload_hash = "0" * 64
    with pytest.raises(Exception):
        db_session.flush()
    savepoint.rollback()


def test_document_missing_snapshot_is_resume_blocked(db_session):
    org, *_rest, project = quality_context(db_session)
    generation = DocumentGenerationJob(
        organization_id=org.id,
        project_id=project.id,
        document_type="basic_design",
        output_format="pdf",
        input_payload_hash="c" * 64,
        status="processing",
    )
    db_session.add(generation)
    db_session.flush()
    DocumentHandler().execute(
        outbox_for(org.id, generation.id, "document_generation_job"),
        WorkerContext(db_session, "resume-worker"),
    )
    assert generation.status == "failed"
    assert generation.resume_block_reason == "immutable_snapshot_missing"


def ai_snapshot(session, tmp_path, score=100):
    org, user, access, project = quality_context(session)
    artifact = Artifact(
        organization_id=org.id,
        project_id=project.id,
        artifact_type="basic_design",
        title="AI source",
        status="revision_requested",
        created_by_user_id=user.id,
    )
    session.add(artifact)
    session.flush()
    storage = LocalArtifactStorage(tmp_path)
    source_id = uuid.uuid4()
    source_key = storage.build_storage_key(
        org.id, project.id, artifact.id, source_id, "source.md"
    )
    source_content = b"immutable source"
    metadata = storage.put_object(source_key, source_content, "text/markdown")
    source = ArtifactVersion(
        id=source_id,
        artifact_id=artifact.id,
        version_number=1,
        storage_key=source_key,
        content_hash=metadata.content_hash,
        mime_type=metadata.mime_type,
        file_size=metadata.size,
        generated_by="human",
        created_by_user_id=user.id,
    )
    session.add(source)
    session.flush()
    artifact.current_version_id = source.id
    review = Review(
        organization_id=org.id,
        project_id=project.id,
        artifact_version_id=source.id,
        review_type="human",
        reviewer_user_id=user.id,
        status="changes_requested",
    )
    session.add(review)
    session.flush()
    comment = ReviewComment(
        review_id=review.id,
        author_user_id=user.id,
        comment_type="issue",
        severity="critical",
        body="Fix the critical issue",
        status="open",
    )
    session.add(comment)
    session.flush()
    workflow = WorkflowJob(
        organization_id=org.id,
        project_id=project.id,
        job_type="auto_revision",
        status="running",
        attempt_count=1,
        max_attempts=3,
    )
    session.add(workflow)
    session.flush()
    comment_identity = [
        {
            "id": str(comment.id),
            "body_hash": hashlib.sha256(comment.body.encode()).hexdigest(),
        }
    ]
    base = canonical_hash(
        {
            "source": str(source.id),
            "comments": comment_identity,
            "attempt": 1,
            "model": "mock-v1",
        }
    )
    version_id = deterministic_uuid(base, "ai-version")
    ai_run_id = deterministic_uuid(base, "ai-run")
    storage_key = storage.build_storage_key(
        org.id, project.id, artifact.id, version_id, "auto-revision-1.md"
    )
    workflow.idempotency_key = base
    snapshot = create_snapshot(
        session,
        input_type="ai_workflow",
        organization_id=org.id,
        project_id=project.id,
        actor_user_id=user.id,
        source_reference_type="artifact_version",
        source_reference_id=source.id,
        workflow_job_id=workflow.id,
        access_context={
            "roles": sorted(access.role_codes),
            "membership": str(access.membership.id),
        },
        settings_snapshot={
            "currency": "JPY",
            "settings_id": None,
            "settings_version": 1,
        },
        payload={
            "source_artifact_version_id": str(source.id),
            "source_content_hash": metadata.content_hash,
            "review_id": str(review.id),
            "unresolved_comment_ids": [str(comment.id)],
            "comment_set_hash": canonical_hash(comment_identity),
            "provider": "openai",
            "model": "mock-v1",
            "operation_type": "revision",
            "prompt_version": "mock-auto-revision-v1",
            "settings_id": None,
            "settings_version": 1,
            "review_threshold": 95,
            "max_auto_revision_count": 3,
            "current_revision_attempt": 1,
            "minute_rate_snapshot": "10.00000000",
            "input_rate_snapshot": "0.10000000",
            "output_rate_snapshot": "0.20000000",
            "target_artifact_id": str(artifact.id),
            "target_version_number": 2,
            "deterministic_target_version_id": str(version_id),
            "ai_run_id": str(ai_run_id),
            "ai_run_idempotency_key": canonical_hash({"run": str(ai_run_id)}),
            "billing_idempotency_key": canonical_hash(
                {"run": str(ai_run_id), "rates": ["10", "0.1", "0.2"]}
            ),
            "requested_by_user_id": str(user.id),
            "mime_type": "text/markdown",
            "storage_key": storage_key,
        },
    )
    from app.services.ai_providers import MockAIProvider

    return (
        org,
        workflow,
        snapshot,
        artifact,
        storage,
        MockAIProvider([score]),
        version_id,
        ai_run_id,
    )


def test_ai_resume_reuses_run_version_review_and_cost(db_session, tmp_path):
    org, workflow, snapshot, artifact, storage, provider, version_id, ai_run_id = (
        ai_snapshot(db_session, tmp_path)
    )
    event = outbox_for(org.id, workflow.id, "workflow_job")
    context = WorkerContext(
        db_session, "resume-worker", storage=storage, ai_provider=provider
    )
    WorkflowHandler().execute(event, context)
    db_session.flush()
    run = db_session.get(AIRun, ai_run_id)
    first_cost = run.calculated_cost
    assert workflow.status == "completed" and artifact.current_version_id == version_id
    counts = (
        db_session.scalar(select(func.count()).select_from(AIRun)),
        db_session.scalar(select(func.count()).select_from(ArtifactVersion)),
        db_session.scalar(select(func.count()).select_from(Review)),
    )
    WorkflowHandler().execute(event, context)
    db_session.flush()
    assert run.calculated_cost == first_cost
    assert counts == (
        db_session.scalar(select(func.count()).select_from(AIRun)),
        db_session.scalar(select(func.count()).select_from(ArtifactVersion)),
        db_session.scalar(select(func.count()).select_from(Review)),
    )
    assert (
        len(
            db_session.scalars(
                select(WorkflowJobStep).where(
                    WorkflowJobStep.workflow_input_id == snapshot.id
                )
            ).all()
        )
        == 9
    )


def test_ai_source_hash_mismatch_and_missing_snapshot_fail_closed(db_session, tmp_path):
    org, workflow, _snapshot, _artifact, storage, provider, *_ = ai_snapshot(
        db_session, tmp_path
    )
    source = db_session.scalar(
        select(ArtifactVersion).where(ArtifactVersion.version_number == 1)
    )
    storage.put_object(source.storage_key, b"tampered", "text/markdown")
    with pytest.raises(Exception, match="source hash"):
        WorkflowHandler().execute(
            outbox_for(org.id, workflow.id, "workflow_job"),
            WorkerContext(
                db_session, "resume-worker", storage=storage, ai_provider=provider
            ),
        )

    org2, *_rest, project2 = quality_context(db_session)
    legacy = WorkflowJob(
        organization_id=org2.id,
        project_id=project2.id,
        job_type="auto_revision",
        status="running",
        attempt_count=1,
        max_attempts=3,
    )
    db_session.add(legacy)
    db_session.flush()
    WorkflowHandler().execute(
        outbox_for(org2.id, legacy.id, "workflow_job"),
        WorkerContext(db_session, "worker"),
    )
    assert (
        legacy.status == "failed"
        and legacy.resume_block_reason == "immutable_snapshot_missing"
    )
