import re
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, object_session

from app.auth.dependencies import (
    AuthenticatedUser,
    OrganizationAccess,
    ensure_resource_organization,
    require_organization_access,
)
from app.models import OrganizationMembership
from app.models.project import (
    AIRun,
    ApprovalEvent,
    Artifact,
    ArtifactVersion,
    Project,
    ProjectMember,
    Review,
    ReviewComment,
)

AI_PASSING_SCORE_DEFAULT = 95
PROJECT_WRITE_ROLES = frozenset(
    {"organization_owner", "organization_admin", "project_manager"}
)
PROJECT_DELETE_ROLES = frozenset({"organization_owner", "organization_admin"})
ARTIFACT_WRITE_ROLES = PROJECT_WRITE_ROLES | {"developer"}
REVIEW_ROLES = PROJECT_WRITE_ROLES | {"reviewer"}
APPROVAL_ROLES = PROJECT_WRITE_ROLES | {"customer"}


def domain_error(message: str, code: int = status.HTTP_409_CONFLICT) -> HTTPException:
    return HTTPException(status_code=code, detail=message)


def require_active_membership(
    session: Session, organization_id: uuid.UUID, user_id: uuid.UUID
) -> None:
    exists = session.scalar(
        select(OrganizationMembership.id).where(
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.user_id == user_id,
            OrganizationMembership.status == "active",
        )
    )
    if exists is None:
        raise domain_error(
            "User is not an active organization member", status.HTTP_403_FORBIDDEN
        )


def create_project(session: Session, access: OrganizationAccess, **values) -> Project:  # type: ignore[no-untyped-def]
    if access.role_codes.isdisjoint(PROJECT_WRITE_ROLES):
        raise domain_error("Permission denied", status.HTTP_403_FORBIDDEN)
    for key in ("customer_user_id", "project_manager_user_id"):
        if values.get(key):
            require_active_membership(
                session, access.membership.organization_id, values[key]
            )
    project = Project(organization_id=access.membership.organization_id, **values)
    session.add(project)
    session.flush()
    return project


def get_project_for_user(
    session: Session, project_id: uuid.UUID, authenticated: AuthenticatedUser
) -> tuple[Project, OrganizationAccess]:
    project = session.get(Project, project_id)
    if project is None or project.archived_at is not None:
        raise domain_error("Project not found", status.HTTP_404_NOT_FOUND)
    access = require_organization_access(
        project.organization_id, authenticated, session
    )
    return project, access


def archive_project(
    project: Project, access: OrganizationAccess, expected_version: int
) -> Project:
    ensure_resource_organization(access, project.organization_id)
    if access.role_codes.isdisjoint(PROJECT_DELETE_ROLES):
        raise domain_error("Permission denied", status.HTTP_403_FORBIDDEN)
    if project.version != expected_version:
        raise domain_error("Project was updated by another request")
    project.archived_at = datetime.now(timezone.utc)
    session = object_session(project)
    if session is not None:
        session.flush()
    return project


def start_project_estimate(
    project: Project, access: OrganizationAccess, expected_version: int
) -> Project:
    ensure_resource_organization(access, project.organization_id)
    if access.role_codes.isdisjoint(PROJECT_WRITE_ROLES):
        raise domain_error("Permission denied", status.HTTP_403_FORBIDDEN)
    if project.version != expected_version:
        raise domain_error("Project was updated by another request")
    if project.status == "estimating" and project.current_phase == "estimate":
        return project
    if project.status not in {"draft", "hearing"} or project.current_phase != "hearing":
        raise domain_error("Project cannot enter estimation from its current state")
    project.status = "estimating"
    project.current_phase = "estimate"
    session = object_session(project)
    if session is not None:
        session.flush()
    return project


def add_project_member(
    session: Session, project: Project, user_id: uuid.UUID, project_role: str
) -> ProjectMember:
    require_active_membership(session, project.organization_id, user_id)
    member = ProjectMember(
        project_id=project.id,
        user_id=user_id,
        project_role=project_role,
        status="active",
    )
    session.add(member)
    session.flush()
    return member


def create_artifact(
    session: Session, project: Project, access: OrganizationAccess, **values
) -> Artifact:  # type: ignore[no-untyped-def]
    ensure_resource_organization(access, project.organization_id)
    if access.role_codes.isdisjoint(ARTIFACT_WRITE_ROLES):
        raise domain_error("Permission denied", status.HTTP_403_FORBIDDEN)
    artifact = Artifact(
        organization_id=project.organization_id, project_id=project.id, **values
    )
    session.add(artifact)
    session.flush()
    return artifact


def add_artifact_version(
    session: Session, artifact: Artifact, access: OrganizationAccess, **values
) -> ArtifactVersion:  # type: ignore[no-untyped-def]
    ensure_resource_organization(access, artifact.organization_id)
    if access.role_codes.isdisjoint(ARTIFACT_WRITE_ROLES):
        raise domain_error("Permission denied", status.HTTP_403_FORBIDDEN)
    next_number = (
        session.scalar(
            select(func.max(ArtifactVersion.version_number)).where(
                ArtifactVersion.artifact_id == artifact.id
            )
        )
        or 0
    ) + 1
    supplied = values.pop("version_number", next_number)
    if supplied != next_number:
        raise domain_error("Artifact version must be the next number")
    if values.get("generated_by") == "ai":
        ai_run = session.get(AIRun, values.get("ai_run_id"))
        if (
            ai_run is None
            or ai_run.organization_id != artifact.organization_id
            or ai_run.project_id != artifact.project_id
        ):
            raise domain_error(
                "AI run does not belong to the artifact project",
                status.HTTP_403_FORBIDDEN,
            )
    version = ArtifactVersion(
        artifact_id=artifact.id, version_number=next_number, **values
    )
    session.add(version)
    session.flush()
    artifact.current_version_id = version.id
    return version


def create_review(
    session: Session,
    version: ArtifactVersion,
    access: OrganizationAccess,
    *,
    passing_score: int = AI_PASSING_SCORE_DEFAULT,
    **values,
) -> Review:  # type: ignore[no-untyped-def]
    artifact = session.get(Artifact, version.artifact_id)
    if artifact is None:
        raise domain_error("Artifact not found", status.HTTP_404_NOT_FOUND)
    ensure_resource_organization(access, artifact.organization_id)
    review_type = values.get("review_type")
    if review_type == "ai":
        if not values.get("ai_run_id") or values.get("reviewer_user_id") is not None:
            raise domain_error("AI review requires only ai_run_id")
        if values.get("status") == "passed" and (
            values.get("score") is None or values["score"] < passing_score
        ):
            raise domain_error("AI review score is below threshold")
        ai_run = session.get(AIRun, values["ai_run_id"])
        if (
            ai_run is None
            or ai_run.organization_id != artifact.organization_id
            or ai_run.project_id != artifact.project_id
        ):
            raise domain_error(
                "AI run does not belong to the artifact project",
                status.HTTP_403_FORBIDDEN,
            )
    elif not values.get("reviewer_user_id") or values.get("ai_run_id") is not None:
        raise domain_error("Human review requires only reviewer_user_id")
    else:
        require_active_membership(
            session, artifact.organization_id, values["reviewer_user_id"]
        )
    review = Review(
        organization_id=artifact.organization_id,
        project_id=artifact.project_id,
        artifact_version_id=version.id,
        **values,
    )
    session.add(review)
    session.flush()
    return review


def add_review_comment(
    session: Session, review: Review, access: OrganizationAccess, **values
) -> ReviewComment:  # type: ignore[no-untyped-def]
    ensure_resource_organization(access, review.organization_id)
    if values.get("author_user_id") is None and review.review_type != "ai":
        raise domain_error("Only AI reviews may have anonymous comments")
    if values.get("author_user_id") is not None:
        require_active_membership(
            session, review.organization_id, values["author_user_id"]
        )
    comment = ReviewComment(review_id=review.id, **values)
    session.add(comment)
    session.flush()
    return comment


def _event(
    session: Session,
    artifact: Artifact,
    version: ArtifactVersion,
    actor_id: uuid.UUID,
    action: str,
    comment: str | None = None,
) -> None:
    session.add(
        ApprovalEvent(
            organization_id=artifact.organization_id,
            project_id=artifact.project_id,
            artifact_version_id=version.id,
            actor_user_id=actor_id,
            action=action,
            comment=comment,
        )
    )


def submit_version(
    session: Session,
    artifact: Artifact,
    version: ArtifactVersion,
    access: OrganizationAccess,
) -> None:
    ensure_resource_organization(access, artifact.organization_id)
    if access.role_codes.isdisjoint(ARTIFACT_WRITE_ROLES):
        raise domain_error("Permission denied", status.HTTP_403_FORBIDDEN)
    if artifact.current_version_id != version.id or artifact.status not in {
        "draft",
        "revision_requested",
    }:
        raise domain_error("Artifact cannot be submitted")
    action = "resubmitted" if artifact.status == "revision_requested" else "submitted"
    artifact.status = "ai_reviewing"
    _event(session, artifact, version, access.user.id, action)
    project = session.get(Project, artifact.project_id)
    if project is not None:
        from app.services.communications import emit_project_event

        emit_project_event(
            session,
            project,
            event_type="artifact_review_requested",
            title="Artifact review requested",
            body=f"Artifact {artifact.title} was submitted for review.",
            severity="info",
            action_url=f"/artifacts/{artifact.id}",
            actor_user_id=access.user.id,
            aggregate_type="artifact",
            aggregate_id=artifact.id,
        )


def move_to_human_review(
    session: Session,
    artifact: Artifact,
    version: ArtifactVersion,
    *,
    passing_score: int = AI_PASSING_SCORE_DEFAULT,
) -> None:
    if artifact.status != "ai_reviewing" or artifact.current_version_id != version.id:
        raise domain_error("Artifact is not awaiting AI review")
    passed = session.scalar(
        select(Review.id).where(
            Review.artifact_version_id == version.id,
            Review.review_type == "ai",
            Review.status == "passed",
            Review.score >= passing_score,
        )
    )
    if passed is None:
        raise domain_error("Passing AI review is required")
    artifact.status = "human_reviewing"


def approve_version(
    session: Session,
    artifact: Artifact,
    version: ArtifactVersion,
    access: OrganizationAccess,
    comment: str | None = None,
) -> None:
    ensure_resource_organization(access, artifact.organization_id)
    if access.role_codes.isdisjoint(APPROVAL_ROLES):
        raise domain_error("Permission denied", status.HTTP_403_FORBIDDEN)
    if (
        artifact.status != "human_reviewing"
        or artifact.current_version_id != version.id
    ):
        raise domain_error("Artifact cannot be approved")
    critical = session.scalar(
        select(ReviewComment.id)
        .join(Review)
        .where(
            Review.artifact_version_id == version.id,
            ReviewComment.severity == "critical",
            ReviewComment.status.in_(["open", "accepted"]),
        )
    )
    if critical is not None:
        raise domain_error("Unresolved critical comments prevent approval")
    artifact.status = "approved"
    _event(session, artifact, version, access.user.id, "approved", comment)
    project = session.get(Project, artifact.project_id)
    if project is not None:
        from app.services.communications import emit_project_event

        emit_project_event(
            session,
            project,
            event_type="artifact_approved",
            title="Artifact approved",
            body=f"Artifact {artifact.title} was approved.",
            severity="success",
            action_url=f"/artifacts/{artifact.id}",
            actor_user_id=access.user.id,
            aggregate_type="artifact",
            aggregate_id=artifact.id,
        )


def request_changes(
    session: Session,
    artifact: Artifact,
    version: ArtifactVersion,
    access: OrganizationAccess,
    comment: str,
) -> None:
    ensure_resource_organization(access, artifact.organization_id)
    if access.role_codes.isdisjoint(REVIEW_ROLES):
        raise domain_error("Permission denied", status.HTTP_403_FORBIDDEN)
    if (
        artifact.status != "human_reviewing"
        or artifact.current_version_id != version.id
    ):
        raise domain_error("Changes cannot be requested")
    artifact.status = "revision_requested"
    _event(session, artifact, version, access.user.id, "changes_requested", comment)
    project = session.get(Project, artifact.project_id)
    if project is not None:
        from app.services.communications import emit_project_event

        emit_project_event(
            session,
            project,
            event_type="artifact_changes_requested",
            title="Artifact changes requested",
            body=f"Changes were requested for artifact {artifact.title}.",
            severity="warning",
            action_url=f"/artifacts/{artifact.id}",
            actor_user_id=access.user.id,
            aggregate_type="artifact",
            aggregate_id=artifact.id,
        )


SECRET_PATTERN = re.compile(r"(?i)(api[_-]?key|token|secret|password)\s*[:=]\s*\S+")


def sanitize_ai_error(message: str | None) -> str | None:
    return SECRET_PATTERN.sub(r"\1=[REDACTED]", message) if message else None


def create_ai_run(
    session: Session,
    *,
    estimated_cost: Decimal | None = None,
    error_message: str | None = None,
    **values,
) -> AIRun:  # type: ignore[no-untyped-def]
    run = AIRun(
        estimated_cost=estimated_cost,
        error_message_sanitized=sanitize_ai_error(error_message),
        **values,
    )
    session.add(run)
    session.flush()
    return run
