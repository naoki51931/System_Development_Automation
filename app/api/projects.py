import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.pagination import paginate_query
from app.api.schemas import (
    ArtifactCreate,
    ArtifactVersionCreate,
    DecisionRequest,
    ProjectCreate,
    ProjectVersionInput,
    ReviewCommentCreate,
    ReviewCreate,
)
from app.auth.dependencies import (
    AuthenticatedUser,
    get_current_user,
    get_session,
    require_organization_access,
)
from app.models.project import Artifact, ArtifactVersion, Project, Review
from app.services.workflow import (
    ARTIFACT_WRITE_ROLES,
    PROJECT_WRITE_ROLES,
    archive_project,
    REVIEW_ROLES,
    add_artifact_version,
    add_review_comment,
    approve_version,
    create_artifact,
    create_project,
    create_review,
    get_project_for_user,
    request_changes,
    start_project_estimate,
    submit_version,
)

router = APIRouter(prefix="/api/v1", tags=["projects"])


def project_json(project: Project) -> dict[str, object]:
    return {
        "id": str(project.id),
        "organization_id": str(project.organization_id),
        "project_code": project.project_code,
        "name": project.name,
        "status": project.status,
        "current_phase": project.current_phase,
        "version": project.version,
    }


@router.post("/projects", status_code=status.HTTP_201_CREATED)
def post_project(
    payload: ProjectCreate,
    authenticated: Annotated[AuthenticatedUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):  # type: ignore[no-untyped-def]
    access = require_organization_access(
        payload.organization_id, authenticated, session, PROJECT_WRITE_ROLES
    )
    project = create_project(
        session,
        access,
        project_code=payload.project_code,
        name=payload.name,
        description=payload.description,
        customer_user_id=payload.customer_user_id,
        project_manager_user_id=payload.project_manager_user_id,
        status="draft",
        current_phase="hearing",
    )
    session.commit()
    return project_json(project)


@router.get("/projects")
def list_projects(
    organization_id: Annotated[uuid.UUID, Query()],
    authenticated: Annotated[AuthenticatedUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    cursor: str | None = None,
    page_size: int = Query(50, ge=1, le=100),
):  # type: ignore[no-untyped-def]
    require_organization_access(organization_id, authenticated, session)
    statement = select(Project).where(
        Project.organization_id == organization_id, Project.archived_at.is_(None)
    )
    return paginate_query(session, statement, Project, cursor, page_size, project_json)


@router.get("/projects/{project_id}")
def get_project(
    project_id: uuid.UUID,
    authenticated: Annotated[AuthenticatedUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):  # type: ignore[no-untyped-def]
    project, _access = get_project_for_user(session, project_id, authenticated)
    return project_json(project)


@router.delete("/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_id: uuid.UUID,
    payload: ProjectVersionInput,
    authenticated: Annotated[AuthenticatedUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    project, access = get_project_for_user(session, project_id, authenticated)
    archive_project(project, access, payload.version)
    session.commit()


@router.post("/projects/{project_id}/start-estimate")
def start_estimate(
    project_id: uuid.UUID,
    payload: ProjectVersionInput,
    authenticated: Annotated[AuthenticatedUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):  # type: ignore[no-untyped-def]
    project, access = get_project_for_user(session, project_id, authenticated)
    start_project_estimate(project, access, payload.version)
    session.commit()
    return project_json(project)


@router.post("/projects/{project_id}/artifacts", status_code=status.HTTP_201_CREATED)
def post_artifact(
    project_id: uuid.UUID,
    payload: ArtifactCreate,
    authenticated: Annotated[AuthenticatedUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):  # type: ignore[no-untyped-def]
    project, access = get_project_for_user(session, project_id, authenticated)
    artifact = create_artifact(
        session,
        project,
        access,
        artifact_type=payload.artifact_type,
        title=payload.title,
        status="draft",
        created_by_user_id=authenticated.user.id,
    )
    session.commit()
    return {"id": str(artifact.id), "status": artifact.status}


@router.post("/artifacts/{artifact_id}/versions", status_code=status.HTTP_201_CREATED)
def post_version(
    artifact_id: uuid.UUID,
    payload: ArtifactVersionCreate,
    authenticated: Annotated[AuthenticatedUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):  # type: ignore[no-untyped-def]
    artifact = session.get(Artifact, artifact_id)
    if artifact is None:
        from fastapi import HTTPException

        raise HTTPException(404, "Artifact not found")
    access = require_organization_access(
        artifact.organization_id, authenticated, session, ARTIFACT_WRITE_ROLES
    )
    version = add_artifact_version(
        session,
        artifact,
        access,
        **payload.model_dump(),
        created_by_user_id=authenticated.user.id,
    )
    session.commit()
    return {"id": str(version.id), "version_number": version.version_number}


def version_context(
    session: Session, version_id: uuid.UUID, authenticated: AuthenticatedUser
):  # type: ignore[no-untyped-def]
    from fastapi import HTTPException

    version = session.get(ArtifactVersion, version_id)
    if version is None:
        raise HTTPException(404, "Version not found")
    artifact = session.get(Artifact, version.artifact_id)
    if artifact is None:
        raise HTTPException(404, "Artifact not found")
    access = require_organization_access(
        artifact.organization_id, authenticated, session
    )
    return version, artifact, access


@router.post(
    "/artifact-versions/{version_id}/reviews", status_code=status.HTTP_201_CREATED
)
def post_review(
    version_id: uuid.UUID,
    payload: ReviewCreate,
    authenticated: Annotated[AuthenticatedUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):  # type: ignore[no-untyped-def]
    version, _artifact, access = version_context(session, version_id, authenticated)
    if access.role_codes.isdisjoint(REVIEW_ROLES):
        from fastapi import HTTPException

        raise HTTPException(403, "Permission denied")
    review = create_review(session, version, access, **payload.model_dump())
    session.commit()
    return {"id": str(review.id), "status": review.status}


@router.post("/reviews/{review_id}/comments", status_code=status.HTTP_201_CREATED)
def post_comment(
    review_id: uuid.UUID,
    payload: ReviewCommentCreate,
    authenticated: Annotated[AuthenticatedUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):  # type: ignore[no-untyped-def]
    from fastapi import HTTPException

    review = session.get(Review, review_id)
    if review is None:
        raise HTTPException(404, "Review not found")
    access = require_organization_access(
        review.organization_id, authenticated, session, REVIEW_ROLES
    )
    values = payload.model_dump()
    if values["author_user_id"] is None and review.review_type != "ai":
        values["author_user_id"] = authenticated.user.id
    comment = add_review_comment(session, review, access, **values, status="open")
    session.commit()
    return {"id": str(comment.id), "status": comment.status}


@router.post("/artifact-versions/{version_id}/submit")
def submit(
    version_id: uuid.UUID,
    authenticated: Annotated[AuthenticatedUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):  # type: ignore[no-untyped-def]
    version, artifact, access = version_context(session, version_id, authenticated)
    submit_version(session, artifact, version, access)
    session.commit()
    return {"status": artifact.status}


@router.post("/artifact-versions/{version_id}/approve")
def approve(
    version_id: uuid.UUID,
    payload: DecisionRequest,
    authenticated: Annotated[AuthenticatedUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):  # type: ignore[no-untyped-def]
    version, artifact, access = version_context(session, version_id, authenticated)
    approve_version(session, artifact, version, access, payload.comment)
    session.commit()
    return {"status": artifact.status}


@router.post("/artifact-versions/{version_id}/request-changes")
def changes(
    version_id: uuid.UUID,
    payload: DecisionRequest,
    authenticated: Annotated[AuthenticatedUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):  # type: ignore[no-untyped-def]
    from fastapi import HTTPException

    if not payload.comment:
        raise HTTPException(422, "Comment is required")
    version, artifact, access = version_context(session, version_id, authenticated)
    request_changes(session, artifact, version, access, payload.comment)
    session.commit()
    return {"status": artifact.status}
