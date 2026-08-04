from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthenticatedUser, require_organization_access
from app.models import MembershipRole, Organization, OrganizationMembership, Role, User
from app.models.project import (
    AIRun,
    ApprovalEvent,
    ArtifactVersion,
    Project,
    ReviewComment,
)
from app.services.workflow import (
    add_artifact_version,
    add_project_member,
    approve_version,
    create_ai_run,
    create_artifact,
    create_project,
    create_review,
    move_to_human_review,
    submit_version,
)


def context(session: Session, suffix: str = "one"):
    organization = Organization(name=f"Org {suffix}", status="active")
    account = User(
        cognito_sub=f"sub-{suffix}",
        email=f"{suffix}@example.com",
        display_name=suffix,
        status="active",
    )
    role = Role(
        code=f"organization_admin_{suffix}", display_name="Admin", is_system=False
    )
    membership = OrganizationMembership(
        organization=organization, user=account, status="active"
    )
    membership.roles.append(MembershipRole(role=role))
    session.add(membership)
    session.flush()
    access = require_organization_access(
        organization.id, AuthenticatedUser(account), session
    )
    return organization, account, access


def project_and_artifact(session: Session):
    organization, account, access = context(session)
    access = type(access)(
        access.user, access.membership, frozenset({"organization_admin"})
    )
    project = create_project(
        session,
        access,
        project_code="P-001",
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
        created_by_user_id=account.id,
    )
    version = add_artifact_version(
        session,
        artifact,
        access,
        storage_key="org/project/artifact/v1.md",
        content_hash="a" * 64,
        mime_type="text/markdown",
        file_size=10,
        generated_by="human",
        created_by_user_id=account.id,
    )
    return organization, account, access, project, artifact, version


def test_project_code_is_unique_inside_organization(db_session: Session):
    organization, account, access = context(db_session)
    access = type(access)(
        access.user, access.membership, frozenset({"organization_admin"})
    )
    db_session.add_all(
        [
            Project(
                organization_id=organization.id,
                project_code="SAME",
                name="A",
                status="draft",
                current_phase="hearing",
            ),
            Project(
                organization_id=organization.id,
                project_code="SAME",
                name="B",
                status="draft",
                current_phase="hearing",
            ),
        ]
    )
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_project_member_requires_membership_and_is_unique(db_session: Session):
    organization, account, access, project, _artifact, _version = project_and_artifact(
        db_session
    )
    add_project_member(db_session, project, account.id, "project_manager")
    with pytest.raises(IntegrityError):
        add_project_member(db_session, project, account.id, "reviewer")
        db_session.flush()


def test_project_member_rejects_user_outside_organization(db_session: Session):
    _organization, _account, _access, project, _artifact, _version = (
        project_and_artifact(db_session)
    )
    outsider = User(
        cognito_sub="member-outsider",
        email="member-outsider@example.com",
        display_name="Out",
        status="active",
    )
    db_session.add(outsider)
    db_session.flush()
    with pytest.raises(HTTPException, match="not an active organization member"):
        add_project_member(db_session, project, outsider.id, "reviewer")


def test_artifact_version_number_is_unique_and_immutable(db_session: Session):
    _organization, _account, _access, _project, _artifact, version = (
        project_and_artifact(db_session)
    )
    db_session.commit()
    version.storage_key = "changed"
    with pytest.raises(DBAPIError, match="immutable"):
        db_session.commit()


def test_artifact_version_number_duplicate_is_rejected(db_session: Session):
    _organization, account, _access, _project, artifact, version = project_and_artifact(
        db_session
    )
    duplicate = ArtifactVersion(
        artifact_id=artifact.id,
        version_number=version.version_number,
        storage_key="duplicate",
        content_hash="b" * 64,
        mime_type="text/plain",
        file_size=1,
        generated_by="human",
        created_by_user_id=account.id,
    )
    db_session.add(duplicate)
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_draft_cannot_be_approved(db_session: Session):
    _organization, _account, access, _project, artifact, version = project_and_artifact(
        db_session
    )
    with pytest.raises(HTTPException, match="cannot be approved"):
        approve_version(db_session, artifact, version, access)


def test_ai_score_threshold_and_critical_comment_block_approval(db_session: Session):
    organization, account, access, project, artifact, version = project_and_artifact(
        db_session
    )
    ai_run = create_ai_run(
        db_session,
        organization_id=organization.id,
        project_id=project.id,
        provider="openai",
        model="test",
        operation_type="review",
        status="completed",
        estimated_cost=Decimal("0.12345678"),
        retry_count=0,
    )
    submit_version(db_session, artifact, version, access)
    with pytest.raises(HTTPException, match="below threshold"):
        create_review(
            db_session,
            version,
            access,
            review_type="ai",
            ai_run_id=ai_run.id,
            status="passed",
            score=94,
        )
    review = create_review(
        db_session,
        version,
        access,
        review_type="ai",
        ai_run_id=ai_run.id,
        status="passed",
        score=95,
    )
    move_to_human_review(db_session, artifact, version)
    db_session.add(
        ReviewComment(
            review_id=review.id,
            comment_type="finding",
            severity="critical",
            body="Critical",
            status="open",
        )
    )
    db_session.flush()
    with pytest.raises(HTTPException, match="critical"):
        approve_version(db_session, artifact, version, access)


def test_review_actor_constraints(db_session: Session):
    organization, account, access, project, _artifact, version = project_and_artifact(
        db_session
    )
    ai_run = AIRun(
        organization_id=organization.id,
        project_id=project.id,
        provider="openai",
        model="test",
        operation_type="review",
        status="completed",
        retry_count=0,
    )
    db_session.add(ai_run)
    db_session.flush()
    with pytest.raises(HTTPException, match="ai_run_id"):
        create_review(db_session, version, access, review_type="ai", status="pending")
    with pytest.raises(HTTPException, match="reviewer_user_id"):
        create_review(
            db_session, version, access, review_type="human", status="pending"
        )


def test_review_rejects_other_organization_actor_and_ai_run(db_session: Session):
    _organization, _account, access, _project, _artifact, version = (
        project_and_artifact(db_session)
    )
    other_org, other_user, _other_access = context(db_session, "other-review")
    other_project = Project(
        organization_id=other_org.id,
        project_code="OTHER",
        name="Other",
        status="draft",
        current_phase="hearing",
    )
    db_session.add(other_project)
    db_session.flush()
    other_run = AIRun(
        organization_id=other_org.id,
        project_id=other_project.id,
        provider="openai",
        model="test",
        operation_type="review",
        status="completed",
        retry_count=0,
    )
    db_session.add(other_run)
    db_session.flush()
    with pytest.raises(HTTPException, match="not an active organization member"):
        create_review(
            db_session,
            version,
            access,
            review_type="human",
            reviewer_user_id=other_user.id,
            status="pending",
        )
    with pytest.raises(HTTPException, match="does not belong"):
        create_review(
            db_session,
            version,
            access,
            review_type="ai",
            ai_run_id=other_run.id,
            status="pending",
        )


def test_approval_events_are_append_only(db_session: Session):
    _organization, _account, access, _project, artifact, version = project_and_artifact(
        db_session
    )
    submit_version(db_session, artifact, version, access)
    db_session.commit()
    event = db_session.query(ApprovalEvent).one()
    event.comment = "changed"
    with pytest.raises(DBAPIError, match="append-only"):
        db_session.commit()
    db_session.rollback()
    event = db_session.query(ApprovalEvent).one()
    db_session.delete(event)
    with pytest.raises(DBAPIError, match="append-only"):
        db_session.commit()


def test_ai_run_sanitizes_error_and_uses_decimal(db_session: Session):
    organization, _account, _access, project, _artifact, _version = (
        project_and_artifact(db_session)
    )
    run = create_ai_run(
        db_session,
        organization_id=organization.id,
        project_id=project.id,
        provider="anthropic",
        model="test",
        operation_type="review",
        status="failed",
        estimated_cost=Decimal("12.12345678"),
        retry_count=2,
        error_message="api_key=topsecret failed",
    )
    db_session.commit()
    assert run.estimated_cost == Decimal("12.12345678")
    assert "topsecret" not in (run.error_message_sanitized or "")
