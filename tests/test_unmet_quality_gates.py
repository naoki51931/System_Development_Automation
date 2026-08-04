import uuid
from datetime import date, timedelta
from decimal import Decimal

import psycopg
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.auth.dependencies import AuthenticatedUser, require_organization_access
from app.main import create_app
from app.models import MembershipRole, Organization, OrganizationMembership, Role, User
from app.models.communications import DocumentGenerationJob, OutboxEvent
from app.models.project import Artifact, ProjectMember
from app.models.project import AIRun, ApprovalEvent, ArtifactVersion
from app.models.communications import EmailMessage, EmailTemplate
from app.services.billing import create_estimate, transition_estimate
from app.services.communications import generate_document
from app.services.storage import LocalArtifactStorage
from app.services.workflow import create_project
from app.services.workflow import move_to_human_review
from app.testing.faults import InjectedFault, database_error_code
from app.workers.outbox import fail


def quality_context(session: Session):
    org = Organization(name=f"failure-{uuid.uuid4()}", status="active")
    user = User(
        cognito_sub=f"failure-{uuid.uuid4()}",
        email=f"{uuid.uuid4()}@quality.local",
        display_name="Quality",
        status="active",
    )
    role = Role(code=f"quality-{uuid.uuid4().hex[:16]}", display_name="Quality")
    membership = OrganizationMembership(organization=org, user=user, status="active")
    membership.roles.append(MembershipRole(role=role))
    session.add(membership)
    session.flush()
    raw = require_organization_access(org.id, AuthenticatedUser(user), session)
    access = type(raw)(
        raw.user,
        raw.membership,
        frozenset(
            {
                "organization_owner",
                "organization_admin",
                "project_manager",
                "reviewer",
                "customer",
            }
        ),
    )
    project = create_project(
        session,
        access,
        project_code=f"Q-{uuid.uuid4().hex[:8]}",
        name="Quality",
        status="draft",
        current_phase="estimate",
    )
    session.add(
        ProjectMember(
            project_id=project.id,
            user_id=user.id,
            project_role="project_manager",
            status="active",
        )
    )
    session.flush()
    return org, user, access, project


def test_document_render_failure_rolls_back_without_public_artifact(
    db_session: Session, tmp_path, monkeypatch
):
    _org, _user, access, project = quality_context(db_session)
    estimate = create_estimate(
        db_session,
        project,
        access,
        estimate_number=f"E-{uuid.uuid4().hex[:8]}",
        valid_until=date.today() + timedelta(days=30),
        include_ai_runs=False,
        include_artifacts=False,
        items=[
            {
                "item_type": "option",
                "description": "Quality",
                "quantity": Decimal("1"),
                "unit": "set",
                "unit_price": Decimal("100"),
            }
        ],
    )
    transition_estimate(db_session, estimate, access, "submit", estimate.version)
    transition_estimate(db_session, estimate, access, "approve", estimate.version)
    before_artifacts = db_session.scalar(select(func.count()).select_from(Artifact))
    before_jobs = db_session.scalar(
        select(func.count()).select_from(DocumentGenerationJob)
    )
    savepoint = db_session.begin_nested()
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("APP_FAULT_INJECTION", "DOCUMENT_RENDER_FAILURE")
    with pytest.raises(InjectedFault) as error:
        generate_document(
            db_session,
            LocalArtifactStorage(tmp_path),
            project,
            access,
            document_type="estimate",
            output_format="pdf",
            source_id=estimate.id,
        )
    assert error.value.code == "DOCUMENT_RENDER_FAILURE" and error.value.retryable
    savepoint.rollback()
    assert (
        db_session.scalar(select(func.count()).select_from(Artifact))
        == before_artifacts
    )
    assert (
        db_session.scalar(select(func.count()).select_from(DocumentGenerationJob))
        == before_jobs
    )
    assert not list(tmp_path.rglob("*"))
    monkeypatch.delenv("APP_FAULT_INJECTION")
    completed = generate_document(
        db_session,
        LocalArtifactStorage(tmp_path),
        project,
        access,
        document_type="estimate",
        output_format="pdf",
        source_id=estimate.id,
    )
    assert (
        completed.status == "completed"
        and completed.content_hash
        and completed.artifact_version_id
    )


def test_postgresql_lock_timeout_is_retryable_and_transaction_rolls_back(
    db_session: Session, database_url: str
):
    org, *_ = quality_context(db_session)
    db_session.commit()
    dsn = database_url.replace("postgresql+psycopg://", "postgresql://")
    first = psycopg.connect(dsn)
    second = psycopg.connect(dsn)
    try:
        first.execute(
            "UPDATE organizations SET name=%s WHERE id=%s", ("locked", org.id)
        )
        second.execute("SET lock_timeout='100ms'")
        with pytest.raises(psycopg.errors.LockNotAvailable) as error:
            second.execute(
                "UPDATE organizations SET name=%s WHERE id=%s", ("partial", org.id)
            )
        assert database_error_code(error.value) == "DATABASE_RETRYABLE"
        second.rollback()
        first.rollback()
        with second.cursor() as cursor:
            cursor.execute("SELECT name FROM organizations WHERE id=%s", (org.id,))
            assert cursor.fetchone()[0] != "partial"
    finally:
        first.close()
        second.close()


def test_database_retry_is_bounded_to_dead_letter(db_session: Session):
    org = Organization(name=f"deadlock-{uuid.uuid4()}")
    db_session.add(org)
    db_session.flush()
    from datetime import datetime, timezone

    job = OutboxEvent(
        organization_id=org.id,
        event_type="database",
        aggregate_type="project",
        aggregate_id=uuid.uuid4(),
        payload_hash=uuid.uuid4().hex.ljust(64, "0"),
        status="processing",
        attempt_count=2,
        max_attempts=2,
        available_at=datetime.now(timezone.utc),
    )
    db_session.add(job)
    db_session.flush()
    fail(db_session, job, "DATABASE_RETRYABLE")
    assert job.status == "dead_letter" and job.last_error_code == "DATABASE_RETRYABLE"
    assert "UPDATE" not in (job.last_error_code or "")


def test_complete_local_business_scenario_uses_real_api_and_mocks(
    db_session: Session, monkeypatch, tmp_path
):
    roles = [
        Role(code=code, display_name=code, is_system=True)
        for code in (
            "customer",
            "project_manager",
            "reviewer",
            "developer",
            "organization_admin",
            "organization_owner",
        )
    ]
    org = Organization(name=f"integration-{uuid.uuid4()}", status="active")
    other = Organization(name=f"other-{uuid.uuid4()}", status="active")
    user = User(
        cognito_sub=f"integration-{uuid.uuid4()}",
        email=f"{uuid.uuid4()}@quality.local",
        display_name="Integration Owner",
        status="active",
    )
    membership = OrganizationMembership(organization=org, user=user, status="active")
    membership.roles.extend(MembershipRole(role=role) for role in roles)
    template = EmailTemplate(
        organization_id=org.id,
        template_code="quality_document",
        name="Quality document",
        subject_template="{{ service_name }} document",
        body_text_template="{{ user_name }} {{ download_url }}",
        locale="ja",
        status="approved",
        version_number=1,
    )
    db_session.add_all([membership, other])
    db_session.flush()
    template.organization_id = org.id
    db_session.add(template)
    db_session.commit()
    app = create_app()
    app.state.session_factory = sessionmaker(
        bind=db_session.get_bind(), expire_on_commit=False
    )
    app.state.storage = LocalArtifactStorage(tmp_path)
    client = TestClient(app)
    users = client.get("/api/v1/auth/local/users")
    assert users.status_code == 200
    login = client.post("/api/v1/auth/local/login", json={"user_id": str(user.id)})
    assert login.status_code == 200
    headers = {"X-CSRF-Token": login.json()["csrf_token"]}

    def post(path, body=None, expected=200):
        response = client.post(f"/api/v1{path}", headers=headers, json=body or {})
        assert response.status_code == expected, response.text
        return response.json()

    project = post(
        "/projects",
        {
            "organization_id": str(org.id),
            "project_code": f"INT-{uuid.uuid4().hex[:8]}",
            "name": "顧客ヒアリング案件",
            "description": "local only",
        },
        201,
    )
    assert client.get(f"/api/v1/projects?organization_id={other.id}").status_code == 403
    estimate = post(
        f"/projects/{project['id']}/estimates",
        {
            "estimate_number": f"EST-{uuid.uuid4().hex[:8]}",
            "currency": "JPY",
            "valid_until": "2099-12-31",
            "items": [
                {
                    "item_type": "option",
                    "description": "品質ゲート",
                    "quantity": "1",
                    "unit": "式",
                    "unit_price": "1000",
                    "source_type": "manual",
                }
            ],
            "include_ai_runs": False,
            "include_artifacts": False,
        },
        201,
    )
    estimate = post(
        f"/estimates/{estimate['id']}/submit", {"version": estimate["version"]}
    )
    estimate = post(
        f"/estimates/{estimate['id']}/approve", {"version": estimate["version"]}
    )
    contract = post(
        f"/estimates/{estimate['id']}/contracts",
        {
            "contract_number": f"CON-{uuid.uuid4().hex[:8]}",
            "contract_type": "development",
            "terms_version": "1",
        },
        201,
    )
    contract = post(
        f"/contracts/{contract['id']}/customer-accept", {"version": contract["version"]}
    )
    contract = post(
        f"/contracts/{contract['id']}/provider-accept", {"version": contract["version"]}
    )
    payment = post(
        f"/contracts/{contract['id']}/payment-intents",
        {
            "idempotency_key": f"quality-{uuid.uuid4()}",
            "expected_amount": estimate["total_amount"],
        },
        201,
    )
    payment = post(
        f"/payment-intents/{payment['id']}/confirm", {"version": payment["version"]}
    )
    assert payment["status"] == "succeeded"
    artifact = post(
        f"/projects/{project['id']}/artifacts",
        {"artifact_type": "requirements_definition", "title": "要件定義"},
        201,
    )
    first = post(
        f"/artifacts/{artifact['id']}/versions",
        {
            "storage_key": f"organizations/{org.id}/v1.md",
            "content_hash": "a" * 64,
            "mime_type": "text/markdown",
            "file_size": 10,
            "generated_by": "human",
            "change_summary": "initial",
        },
        201,
    )
    post(f"/artifact-versions/{first['id']}/submit")
    low_run = AIRun(
        organization_id=org.id,
        project_id=uuid.UUID(project["id"]),
        provider="openai",
        model="quality",
        operation_type="review",
        status="completed",
        input_tokens=5,
        output_tokens=5,
        estimated_cost=Decimal("0.005"),
        retry_count=0,
    )
    pass_run = AIRun(
        organization_id=org.id,
        project_id=uuid.UUID(project["id"]),
        provider="openai",
        model="quality",
        operation_type="review",
        status="completed",
        input_tokens=5,
        output_tokens=5,
        estimated_cost=Decimal("0.005"),
        retry_count=0,
    )
    db_session.add_all([low_run, pass_run])
    db_session.commit()
    post(
        f"/artifact-versions/{first['id']}/reviews",
        {
            "review_type": "ai",
            "ai_run_id": str(low_run.id),
            "status": "changes_requested",
            "score": 50,
            "summary": "threshold failed",
        },
        201,
    )
    post(
        f"/artifact-versions/{first['id']}/reviews",
        {
            "review_type": "ai",
            "ai_run_id": str(pass_run.id),
            "status": "passed",
            "score": 95,
            "summary": "manual escalation prerequisite",
        },
        201,
    )
    human = post(
        f"/artifact-versions/{first['id']}/reviews",
        {
            "review_type": "human",
            "reviewer_user_id": str(user.id),
            "status": "changes_requested",
            "score": 50,
            "summary": "threshold failed",
        },
        201,
    )
    post(
        f"/reviews/{human['id']}/comments",
        {"severity": "critical", "body": "critical change required"},
        201,
    )
    first_version = db_session.get(ArtifactVersion, uuid.UUID(first["id"]))
    first_artifact = db_session.get(Artifact, first_version.artifact_id)
    move_to_human_review(db_session, first_artifact, first_version)
    db_session.commit()
    post(
        f"/artifact-versions/{first['id']}/request-changes",
        {"comment": "fix critical issue"},
    )
    ai_run = AIRun(
        organization_id=org.id,
        project_id=uuid.UUID(project["id"]),
        provider="openai",
        model="quality",
        operation_type="revision",
        status="completed",
        input_tokens=10,
        output_tokens=10,
        estimated_cost=Decimal("0.01"),
        retry_count=0,
    )
    db_session.add(ai_run)
    db_session.commit()
    second = post(
        f"/artifacts/{artifact['id']}/versions",
        {
            "storage_key": f"organizations/{org.id}/v2.md",
            "content_hash": "b" * 64,
            "mime_type": "text/markdown",
            "file_size": 20,
            "generated_by": "ai",
            "ai_run_id": str(ai_run.id),
            "change_summary": "mock AI revision",
        },
        201,
    )
    assert second["id"] != first["id"]
    post(f"/artifact-versions/{second['id']}/submit")
    ai_review = AIRun(
        organization_id=org.id,
        project_id=uuid.UUID(project["id"]),
        provider="openai",
        model="quality",
        operation_type="review",
        status="completed",
        input_tokens=10,
        output_tokens=10,
        estimated_cost=Decimal("0.02"),
        retry_count=0,
    )
    db_session.add(ai_review)
    db_session.commit()
    post(
        f"/artifact-versions/{second['id']}/reviews",
        {
            "review_type": "ai",
            "ai_run_id": str(ai_review.id),
            "status": "passed",
            "score": 95,
            "summary": "threshold met",
        },
        201,
    )
    db_session.expire_all()
    current = db_session.get(ArtifactVersion, uuid.UUID(second["id"]))
    current_artifact = db_session.get(Artifact, current.artifact_id)
    move_to_human_review(db_session, current_artifact, current)
    db_session.commit()
    post(f"/artifact-versions/{second['id']}/approve", {"comment": "human approved"})
    estimate_pdf = post(
        f"/projects/{project['id']}/documents/generate",
        {
            "document_type": "estimate",
            "output_format": "pdf",
            "source_id": estimate["id"],
        },
        201,
    )
    document = post(
        f"/projects/{project['id']}/documents/generate",
        {"document_type": "basic_design", "output_format": "pdf"},
        201,
    )
    assert (
        estimate_pdf["content_hash"]
        and document["content_hash"]
        and document["file_size"] > 0
    )
    db_session.expire_all()
    generated_artifact = db_session.get(Artifact, uuid.UUID(document["artifact_id"]))
    generated_artifact.status = "approved"
    db_session.commit()
    mail_body = {
        "recipient_user_id": str(user.id),
        "template_code": "quality_document",
        "expires_seconds": 3600,
        "deduplication_key": f"document-{document['id']}",
    }
    sent = post(
        f"/artifact-versions/{document['artifact_version_id']}/send-email", mail_body
    )
    again = post(
        f"/artifact-versions/{document['artifact_version_id']}/send-email", mail_body
    )
    assert sent["id"] == again["id"] and sent["status"] == "delivered"
    room = post(
        f"/projects/{project['id']}/chat-rooms",
        {"room_type": "project", "name": "追加修正"},
        201,
    )
    message = post(
        f"/chat-rooms/{room['id']}/messages",
        {"body": "追加修正をお願いします", "message_type": "user"},
        201,
    )
    request = post(
        f"/chat-messages/{message['id']}/change-requests",
        {
            "title": "追加修正",
            "description": "影響分析対象",
            "priority": "normal",
            "scope_type": "minor_change",
        },
        201,
    )
    request = post(
        f"/change-requests/{request['id']}/analyze", {"version": request["version"]}
    )
    request = post(
        f"/change-requests/{request['id']}/approve", {"version": request["version"]}
    )
    assert request["status"] == "approved"
    extra = post(
        f"/projects/{project['id']}/estimates",
        {
            "estimate_number": f"ADD-{uuid.uuid4().hex[:8]}",
            "currency": "JPY",
            "valid_until": "2099-12-31",
            "items": [
                {
                    "item_type": "option",
                    "description": "追加修正",
                    "quantity": "1",
                    "unit": "式",
                    "unit_price": "500",
                    "source_type": "manual",
                }
            ],
            "include_ai_runs": False,
            "include_artifacts": False,
        },
        201,
    )
    assert extra["total_amount"] == "550.00000000"
    with sessionmaker(bind=db_session.get_bind())() as verify:
        assert (
            verify.get(ArtifactVersion, uuid.UUID(first["id"])).content_hash == "a" * 64
        )
        assert (
            verify.scalar(
                select(func.count())
                .select_from(AIRun)
                .where(AIRun.organization_id == org.id)
            )
            >= 4
        )
        assert (
            verify.scalar(
                select(func.count())
                .select_from(ApprovalEvent)
                .where(ApprovalEvent.organization_id == org.id)
            )
            >= 1
        )
        assert (
            verify.scalar(
                select(func.count())
                .select_from(DocumentGenerationJob)
                .where(
                    DocumentGenerationJob.organization_id == org.id,
                    DocumentGenerationJob.content_hash.is_not(None),
                )
            )
            == 2
        )
        assert (
            verify.scalar(
                select(func.count())
                .select_from(EmailMessage)
                .where(EmailMessage.organization_id == org.id)
            )
            == 1
        )
        assert (
            verify.scalar(
                select(func.count())
                .select_from(OutboxEvent)
                .where(OutboxEvent.organization_id == org.id)
            )
            >= 1
        )
