import hashlib
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthenticatedUser, require_organization_access
from app.errors import AppError
from app.models import (
    AuditLog,
    MembershipRole,
    Organization,
    OrganizationMembership,
    Role,
    User,
)
from app.models.automation import AISetting
from app.models.project import AIRun, ArtifactVersion, Review, ReviewComment
from app.services.ai_providers import (
    AIProviderUnavailable,
    AnthropicProviderStub,
    MockAIProvider,
    OpenAIProviderStub,
)
from app.services.automation import (
    ResolvedAISetting,
    apply_ai_cost,
    calculate_ai_cost,
    resolve_ai_setting,
    run_auto_revision,
    transition_comment,
    update_ai_setting,
)
from app.services.storage import LocalArtifactStorage
from app.services.workflow import add_artifact_version, create_artifact, create_project


def make_context(session: Session):
    organization = Organization(name="Automation Org", status="active")
    user = User(
        cognito_sub=f"automation-{uuid.uuid4()}",
        email=f"{uuid.uuid4()}@example.com",
        display_name="Admin",
        status="active",
    )
    role = Role(
        code=f"auto-{uuid.uuid4().hex[:20]}", display_name="Admin", is_system=False
    )
    membership = OrganizationMembership(
        organization=organization, user=user, status="active"
    )
    membership.roles.append(MembershipRole(role=role))
    session.add(membership)
    session.flush()
    raw = require_organization_access(organization.id, AuthenticatedUser(user), session)
    access = type(raw)(
        raw.user, raw.membership, frozenset({"organization_admin", "reviewer"})
    )
    project = create_project(
        session,
        access,
        project_code=f"P-{uuid.uuid4()}",
        name="Project",
        status="draft",
        current_phase="hearing",
    )
    artifact = create_artifact(
        session,
        project,
        access,
        artifact_type="requirements_definition",
        title="Requirements",
        status="draft",
        created_by_user_id=user.id,
    )
    return organization, user, access, project, artifact


@pytest.mark.parametrize(("duration", "minutes"), [(1000, 1), (60000, 1), (61000, 2)])
def test_ai_cost_rounds_minutes_up(duration: int, minutes: int):
    billed, cost = calculate_ai_cost(
        duration,
        2,
        3,
        Decimal("1.00000001"),
        Decimal("0.10000001"),
        Decimal("0.20000001"),
    )
    assert billed == minutes
    assert cost == (
        Decimal(minutes) * Decimal("1.00000001")
        + Decimal(2) * Decimal("0.10000001")
        + Decimal(3) * Decimal("0.20000001")
    ).quantize(Decimal("0.00000001"))


def test_ai_cost_snapshots_do_not_change():
    run = AIRun(
        organization_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        provider="openai",
        model="mock",
        operation_type="revision",
        status="completed",
        duration_ms=1,
        input_tokens=10,
        output_tokens=20,
        retry_count=0,
    )
    original = ResolvedAISetting(
        "openai",
        "mock",
        "revision",
        minute_rate=Decimal("2.12345678"),
        token_input_rate=Decimal("0.00000001"),
        token_output_rate=Decimal("0.00000002"),
    )
    apply_ai_cost(run, original)
    recorded = run.calculated_cost
    changed = ResolvedAISetting(
        "openai",
        "mock",
        "revision",
        minute_rate=Decimal("999"),
        token_input_rate=Decimal("9"),
        token_output_rate=Decimal("9"),
    )
    assert run.calculated_cost == recorded
    assert run.minute_rate_snapshot != changed.minute_rate
    assert run.estimated_cost == recorded


def test_ai_setting_resolution_project_then_organization_then_system(
    db_session: Session,
):
    organization, _user, _access, project, _artifact = make_context(db_session)
    organization_setting = AISetting(
        organization_id=organization.id,
        provider="openai",
        model="mock",
        operation_type="revision",
        review_threshold=80,
        max_auto_revision_count=2,
        minute_rate=Decimal("1"),
        token_input_rate=Decimal("0"),
        token_output_rate=Decimal("0"),
    )
    project_setting = AISetting(
        organization_id=organization.id,
        project_id=project.id,
        provider="openai",
        model="mock",
        operation_type="revision",
        review_threshold=98,
        max_auto_revision_count=4,
        minute_rate=Decimal("2"),
        token_input_rate=Decimal("0"),
        token_output_rate=Decimal("0"),
    )
    db_session.add_all([organization_setting, project_setting])
    db_session.flush()
    assert (
        resolve_ai_setting(
            db_session, organization.id, project.id, "openai", "mock", "revision"
        ).review_threshold
        == 98
    )
    assert (
        resolve_ai_setting(
            db_session, organization.id, uuid.uuid4(), "openai", "mock", "revision"
        ).review_threshold
        == 80
    )
    default = resolve_ai_setting(
        db_session, organization.id, project.id, "anthropic", "none", "review"
    )
    assert default.source == "system"
    assert default.review_threshold == 95


def test_ai_setting_optimistic_lock_conflict(db_session: Session):
    organization, _user, _access, _project, _artifact = make_context(db_session)
    setting = AISetting(
        organization_id=organization.id,
        provider="openai",
        model="mock",
        operation_type="review",
        review_threshold=95,
        max_auto_revision_count=3,
        minute_rate=Decimal("0"),
        token_input_rate=Decimal("0"),
        token_output_rate=Decimal("0"),
    )
    db_session.add(setting)
    db_session.flush()
    update_ai_setting(db_session, setting, 1, {"review_threshold": 96})
    with pytest.raises(AppError, match="updated by another"):
        update_ai_setting(db_session, setting, 1, {"review_threshold": 97})


def test_local_storage_validation_and_tenant_key(tmp_path):
    storage = LocalArtifactStorage(tmp_path, max_file_size=5)
    ids = [uuid.uuid4() for _ in range(4)]
    key = storage.build_storage_key(*ids, "result.md")
    assert (
        key
        == f"organizations/{ids[0]}/projects/{ids[1]}/artifacts/{ids[2]}/versions/{ids[3]}/result.md"
    )
    content = b"hello"
    metadata = storage.put_object(key, content, "text/markdown")
    assert metadata.content_hash == hashlib.sha256(content).hexdigest()
    assert storage.get_object(key) == content
    with pytest.raises(AppError) as traversal:
        storage.build_storage_key(*ids, "../secret")
    assert traversal.value.code == "INVALID_REQUEST"
    with pytest.raises(AppError) as mime:
        storage.put_object(key, b"x", "text/html")
    assert mime.value.code == "UNSUPPORTED_MEDIA_TYPE"
    with pytest.raises(AppError) as large:
        storage.put_object(key, b"123456", "text/plain")
    assert large.value.code == "FILE_TOO_LARGE"
    with pytest.raises(AppError):
        storage.delete_unapproved_object(key, approved=True)


def test_external_provider_stubs_never_communicate():
    for provider in (OpenAIProviderStub(), AnthropicProviderStub()):
        assert provider.test_connection() is False
        with pytest.raises(AIProviderUnavailable):
            provider.review(b"secret")


def test_comment_transitions_audit_and_version(db_session: Session):
    organization, user, access, project, artifact = make_context(db_session)
    version = add_artifact_version(
        db_session,
        artifact,
        access,
        storage_key="local",
        content_hash="a" * 64,
        mime_type="text/markdown",
        file_size=1,
        generated_by="human",
        created_by_user_id=user.id,
    )
    review = Review(
        organization_id=organization.id,
        project_id=project.id,
        artifact_version_id=version.id,
        review_type="human",
        reviewer_user_id=user.id,
        status="changes_requested",
    )
    comment = ReviewComment(
        review_id=uuid.uuid4(),
        comment_type="finding",
        severity="major",
        body="Fix",
        status="open",
    )
    db_session.add(review)
    db_session.flush()
    comment.review_id = review.id
    db_session.add(comment)
    db_session.flush()
    transition_comment(db_session, comment, review, access, "accepted", uuid.uuid4(), 1)
    assert comment.status == "accepted"
    assert review.version == 2
    assert (
        db_session.scalar(select(AuditLog).where(AuditLog.resource_id == comment.id))
        is not None
    )
    with pytest.raises(AppError) as conflict:
        transition_comment(
            db_session, comment, review, access, "resolved", uuid.uuid4(), 1
        )
    assert conflict.value.code == "VERSION_CONFLICT"
    transition_comment(db_session, comment, review, access, "resolved", uuid.uuid4(), 2)
    assert comment.resolved_by_user_id == user.id
    assert comment.resolved_at is not None


def test_auto_revision_creates_immutable_new_version_and_cost(
    db_session: Session, tmp_path
):
    organization, user, access, project, artifact = make_context(db_session)
    storage = LocalArtifactStorage(tmp_path)
    source_id = uuid.uuid4()
    source_key = storage.build_storage_key(
        organization.id, project.id, artifact.id, source_id, "source.md"
    )
    metadata = storage.put_object(source_key, b"original", "text/markdown")
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
    db_session.add(source)
    db_session.flush()
    artifact.current_version_id = source.id
    artifact.status = "revision_requested"
    review = Review(
        organization_id=organization.id,
        project_id=project.id,
        artifact_version_id=source.id,
        review_type="human",
        reviewer_user_id=user.id,
        status="changes_requested",
    )
    db_session.add(review)
    db_session.flush()
    db_session.add(
        ReviewComment(
            review_id=review.id,
            comment_type="finding",
            severity="critical",
            body="Fix critical",
            status="open",
        )
    )
    db_session.flush()
    setting = ResolvedAISetting(
        "openai",
        "mock",
        "revision",
        review_threshold=95,
        max_auto_revision_count=2,
        minute_rate=Decimal("1.00000000"),
        token_input_rate=Decimal("0.01000000"),
        token_output_rate=Decimal("0.02000000"),
    )
    job = run_auto_revision(
        db_session, storage, MockAIProvider([50, 99]), artifact, access, setting
    )
    assert job.status == "completed"
    assert job.attempt_count == 2
    assert storage.get_object(source.storage_key) == b"original"
    versions = db_session.scalars(
        select(ArtifactVersion)
        .where(ArtifactVersion.artifact_id == artifact.id)
        .order_by(ArtifactVersion.version_number)
    ).all()
    assert len(versions) == 3
    assert artifact.status == "human_reviewing"
    runs = db_session.scalars(select(AIRun).where(AIRun.project_id == project.id)).all()
    assert len(runs) == 2
    assert all(
        run.calculated_cost is not None
        and run.minute_rate_snapshot == Decimal("1.00000000")
        for run in runs
    )


def test_auto_revision_escalates_at_limit(db_session: Session, tmp_path):
    organization, user, access, project, artifact = make_context(db_session)
    storage = LocalArtifactStorage(tmp_path)
    source_id = uuid.uuid4()
    key = storage.build_storage_key(
        organization.id, project.id, artifact.id, source_id, "source.md"
    )
    metadata = storage.put_object(key, b"original", "text/markdown")
    source = ArtifactVersion(
        id=source_id,
        artifact_id=artifact.id,
        version_number=1,
        storage_key=key,
        content_hash=metadata.content_hash,
        mime_type=metadata.mime_type,
        file_size=metadata.size,
        generated_by="human",
        created_by_user_id=user.id,
    )
    db_session.add(source)
    db_session.flush()
    artifact.current_version_id = source.id
    artifact.status = "revision_requested"
    job = run_auto_revision(
        db_session,
        storage,
        MockAIProvider([1, 2]),
        artifact,
        access,
        ResolvedAISetting("openai", "mock", "revision", max_auto_revision_count=2),
    )
    assert job.status == "escalated"
    assert job.last_error_code == "AI_RETRY_LIMIT_REACHED"
    assert job.attempt_count == 2
