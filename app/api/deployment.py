import json
import uuid
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.automation import get_storage
from app.auth.dependencies import (
    AuthenticatedUser,
    get_current_user,
    get_session,
    require_organization_access,
)
from app.auth.permissions import Permission, require_permission
from app.models import DeploymentPlan, Project
from app.models import DeploymentExecution
from app.services.deployment import (
    create_deployment_plan,
    evaluate_staging_plan,
    request_staging_approval,
    security_check_plan,
)
from app.services.storage import ArtifactStorage
from app.services.terraform_executor import (
    ExecutionEnvironmentContext,
    SafeStagingTerraformExecutor,
)

router = APIRouter(prefix="/api/v1/deployment-plans", tags=["staging-deployment-gate"])
execution_router = APIRouter(
    prefix="/api/v1/deployment-executions", tags=["staging-execution-preparation"]
)


class DeploymentPlanCreate(BaseModel):
    project_id: uuid.UUID
    plan: dict[str, Any]
    terraform_root: str = Field(min_length=1, max_length=1024)
    terraform_workspace: str | None = Field(default=None, max_length=255)
    terraform_state_identity: str | None = Field(default=None, max_length=1024)
    aws_account_id: str | None = Field(default=None, max_length=32)
    aws_region: str | None = Field(default=None, max_length=64)


class SecurityCheckRequest(BaseModel):
    expected_account_id: str = Field(min_length=1, max_length=32)
    expected_region: str = Field(min_length=1, max_length=64)
    expected_root: str = Field(min_length=1, max_length=1024)
    expected_state_identity: str = Field(min_length=1, max_length=1024)


class AuthorizeRequest(BaseModel):
    current_plan_sha256: str = Field(min_length=64, max_length=64)
    current_state_identity: str = Field(min_length=1, max_length=1024)
    current_account_id: str = Field(min_length=1, max_length=32)
    current_region: str = Field(min_length=1, max_length=64)


class ExecutionContextRequest(BaseModel):
    aws_account_id: str | None = Field(default=None, max_length=32)
    aws_region: str | None = Field(default=None, max_length=64)
    terraform_root: str | None = Field(default=None, max_length=1024)
    state_identity: str | None = Field(default=None, max_length=1024)
    environment: str | None = Field(default=None, max_length=30)


def plan_json(plan: DeploymentPlan) -> dict[str, Any]:
    return {
        "id": str(plan.id),
        "organization_id": str(plan.organization_id),
        "project_id": str(plan.project_id),
        "environment": plan.environment,
        "target_environment": plan.target_environment,
        "status": plan.status,
        "created_by": str(plan.created_by_user_id),
        "created_at": plan.created_at.isoformat() if plan.created_at else None,
        "plan_sha256": plan.plan_sha256,
        "plan_size": plan.plan_size,
        "plan_format_version": plan.plan_format_version,
        "terraform_root": plan.terraform_root,
        "terraform_workspace": plan.terraform_workspace,
        "terraform_state_identity": plan.terraform_state_identity,
        "aws_account_id": plan.aws_account_id,
        "aws_region": plan.aws_region,
        "plan_summary": plan.plan_summary,
        "security_gate_status": plan.security_gate_status,
        "security_gate_result": plan.security_gate_result,
        "approval_id": str(plan.approval_id) if plan.approval_id else None,
        "superseded_by": str(plan.superseded_by_id) if plan.superseded_by_id else None,
        "executed_at": plan.executed_at.isoformat() if plan.executed_at else None,
    }


def get_plan(plan_id: uuid.UUID, session: Session) -> DeploymentPlan:
    plan = session.get(DeploymentPlan, plan_id)
    if plan is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Deployment plan not found")
    return plan


def execution_json(execution: DeploymentExecution) -> dict[str, Any]:
    return {
        "id": str(execution.id),
        "organization_id": str(execution.organization_id),
        "project_id": str(execution.project_id),
        "deployment_plan_id": str(execution.deployment_plan_id),
        "approval_id": str(execution.approval_id),
        "requested_by": str(execution.requested_by),
        "requested_at": execution.requested_at.isoformat()
        if execution.requested_at
        else None,
        "plan_sha256": execution.plan_sha256,
        "status": execution.status,
        "authorization_result": execution.authorization_result,
        "authorization_reason": execution.authorization_reason,
        "evidence": execution.evidence,
        "prepared_at": execution.prepared_at.isoformat()
        if execution.prepared_at
        else None,
        "executed_at": execution.executed_at.isoformat()
        if execution.executed_at
        else None,
        "correlation_id": str(execution.correlation_id),
    }


def _context(payload: ExecutionContextRequest) -> ExecutionEnvironmentContext:
    return ExecutionEnvironmentContext(
        payload.aws_account_id,
        payload.aws_region,
        payload.terraform_root,
        payload.state_identity,
        payload.environment,
    )


@router.post("", status_code=status.HTTP_201_CREATED)
def create_plan(
    payload: DeploymentPlanCreate,
    request: Request,
    authenticated: Annotated[AuthenticatedUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    storage: Annotated[ArtifactStorage, Depends(get_storage)],
):
    project = session.get(Project, payload.project_id)
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
    access = require_organization_access(
        project.organization_id, authenticated, session
    )
    plan = create_deployment_plan(
        session,
        storage,
        access,
        project_id=payload.project_id,
        plan_document=payload.plan,
        terraform_root=payload.terraform_root,
        terraform_workspace=payload.terraform_workspace,
        terraform_state_identity=payload.terraform_state_identity,
        aws_account_id=payload.aws_account_id,
        aws_region=payload.aws_region,
        request_id=uuid.uuid4(),
    )
    session.commit()
    return plan_json(plan)


@router.get("")
def list_plans(
    organization_id: uuid.UUID,
    authenticated: Annotated[AuthenticatedUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    access = require_organization_access(organization_id, authenticated, session)
    require_permission(session, access, Permission.DEPLOYMENT_READ)
    return [
        plan_json(plan)
        for plan in session.scalars(
            select(DeploymentPlan)
            .where(DeploymentPlan.organization_id == organization_id)
            .order_by(DeploymentPlan.created_at.desc())
        ).all()
    ]


@router.get("/{plan_id}")
def read_plan(
    plan_id: uuid.UUID,
    authenticated: Annotated[AuthenticatedUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    plan = get_plan(plan_id, session)
    access = require_organization_access(plan.organization_id, authenticated, session)
    require_permission(session, access, Permission.DEPLOYMENT_READ, plan.project_id)
    return plan_json(plan)


@router.post("/{plan_id}/security-check")
def check_plan(
    plan_id: uuid.UUID,
    payload: SecurityCheckRequest,
    authenticated: Annotated[AuthenticatedUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    storage: Annotated[ArtifactStorage, Depends(get_storage)],
):
    plan = get_plan(plan_id, session)
    access = require_organization_access(plan.organization_id, authenticated, session)
    document = json.loads(storage.get_object(plan.plan_storage_key))
    result = security_check_plan(
        session,
        access,
        plan,
        document,
        expected_account_id=payload.expected_account_id,
        expected_region=payload.expected_region,
        expected_root=payload.expected_root,
        expected_state_identity=payload.expected_state_identity,
        request_id=uuid.uuid4(),
    )
    session.commit()
    return {
        "status": result.status,
        "reasons": list(result.reasons),
        "summary": result.summary,
    }


@router.post("/{plan_id}/request-approval", status_code=status.HTTP_201_CREATED)
def request_plan_approval(
    plan_id: uuid.UUID,
    authenticated: Annotated[AuthenticatedUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    plan = get_plan(plan_id, session)
    access = require_organization_access(plan.organization_id, authenticated, session)
    approval = request_staging_approval(session, access, plan, request_id=uuid.uuid4())
    session.commit()
    return {
        "approval_id": str(approval.id),
        "plan_sha256": approval.plan_checksum,
        "status": approval.status,
    }


@router.post("/{plan_id}/authorize")
def authorize_plan(
    plan_id: uuid.UUID,
    payload: AuthorizeRequest,
    authenticated: Annotated[AuthenticatedUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    plan = get_plan(plan_id, session)
    access = require_organization_access(plan.organization_id, authenticated, session)
    decision = evaluate_staging_plan(
        session,
        access,
        plan,
        current_plan_sha256=payload.current_plan_sha256,
        current_state_identity=payload.current_state_identity,
        current_account_id=payload.current_account_id,
        current_region=payload.current_region,
        request_id=uuid.uuid4(),
    )
    session.commit()
    return {
        "authorized": decision.allowed,
        "reason": decision.reason,
        "plan_id": str(plan.id),
    }


@router.post("/{plan_id}/execution-requests", status_code=status.HTTP_201_CREATED)
def request_execution(
    plan_id: uuid.UUID,
    payload: ExecutionContextRequest,
    authenticated: Annotated[AuthenticatedUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    storage: Annotated[ArtifactStorage, Depends(get_storage)],
):
    plan = get_plan(plan_id, session)
    access = require_organization_access(plan.organization_id, authenticated, session)
    execution = SafeStagingTerraformExecutor(
        storage, repository_root=Path(__file__).resolve().parents[2]
    ).request(session, access, plan, context=_context(payload), request_id=uuid.uuid4())
    session.commit()
    return execution_json(execution)


@execution_router.get("/{execution_id}")
def read_execution(
    execution_id: uuid.UUID,
    authenticated: Annotated[AuthenticatedUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    execution = session.get(DeploymentExecution, execution_id)
    if execution is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Deployment execution not found")
    access = require_organization_access(
        execution.organization_id, authenticated, session
    )
    require_permission(
        session, access, Permission.DEPLOYMENT_READ, execution.project_id
    )
    return execution_json(execution)


@execution_router.post("/{execution_id}/prepare")
def prepare_execution(
    execution_id: uuid.UUID,
    payload: ExecutionContextRequest,
    authenticated: Annotated[AuthenticatedUser, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    storage: Annotated[ArtifactStorage, Depends(get_storage)],
):
    execution = session.get(DeploymentExecution, execution_id)
    if execution is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Deployment execution not found")
    access = require_organization_access(
        execution.organization_id, authenticated, session
    )
    require_permission(
        session, access, Permission.DEPLOYMENT_READ, execution.project_id
    )
    prepared = SafeStagingTerraformExecutor(
        storage, repository_root=Path(__file__).resolve().parents[2]
    ).prepare(
        session, access, execution, context=_context(payload), request_id=uuid.uuid4()
    )
    session.commit()
    return execution_json(prepared)
