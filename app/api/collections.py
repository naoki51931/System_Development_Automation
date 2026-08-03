import uuid
from typing import Annotated
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.api.pagination import paginate_query
from app.auth.dependencies import AuthenticatedUser, get_current_user, get_session, require_organization_access
from app.models import Artifact, AuditLog, DocumentGenerationJob, EmailMessage, OutboxEvent, Review, WorkflowJob
router=APIRouter(prefix="/api/v1",tags=["cursor-collections"])

def simple(x):
    fields=("id","organization_id","project_id","status","created_at","event_type","job_type","artifact_type","title","review_type","score","attempt_count","max_attempts","last_error_code","version")
    return {f:(v.isoformat() if hasattr(v,"isoformat") else str(v) if isinstance(v,uuid.UUID) else v) for f in fields if (v:=getattr(x,f,None)) is not None}

def collection(model, organization_id, auth, session, cursor, page_size, admin=False):
    access=require_organization_access(organization_id,auth,session)
    if admin and access.role_codes.isdisjoint({"organization_owner","organization_admin"}):
        from fastapi import HTTPException; raise HTTPException(403,"Permission denied")
    return paginate_query(session,select(model).where(model.organization_id==organization_id),model,cursor,page_size,simple)

@router.get("/artifacts")
def artifacts(organization_id:uuid.UUID,authenticated:Annotated[AuthenticatedUser,Depends(get_current_user)],session:Annotated[Session,Depends(get_session)],cursor:str|None=None,page_size:int=Query(50,ge=1,le=100)):return collection(Artifact,organization_id,authenticated,session,cursor,page_size)
@router.get("/reviews")
def reviews(organization_id:uuid.UUID,authenticated:Annotated[AuthenticatedUser,Depends(get_current_user)],session:Annotated[Session,Depends(get_session)],cursor:str|None=None,page_size:int=Query(50,ge=1,le=100)):return collection(Review,organization_id,authenticated,session,cursor,page_size)
@router.get("/email-messages")
def emails(organization_id:uuid.UUID,authenticated:Annotated[AuthenticatedUser,Depends(get_current_user)],session:Annotated[Session,Depends(get_session)],cursor:str|None=None,page_size:int=Query(50,ge=1,le=100)):return collection(EmailMessage,organization_id,authenticated,session,cursor,page_size,True)
@router.get("/document-generation-jobs")
def documents(organization_id:uuid.UUID,authenticated:Annotated[AuthenticatedUser,Depends(get_current_user)],session:Annotated[Session,Depends(get_session)],cursor:str|None=None,page_size:int=Query(50,ge=1,le=100)):return collection(DocumentGenerationJob,organization_id,authenticated,session,cursor,page_size,True)
@router.get("/workflow-jobs")
def workflows(organization_id:uuid.UUID,authenticated:Annotated[AuthenticatedUser,Depends(get_current_user)],session:Annotated[Session,Depends(get_session)],cursor:str|None=None,page_size:int=Query(50,ge=1,le=100)):return collection(WorkflowJob,organization_id,authenticated,session,cursor,page_size,True)
@router.get("/outbox-events")
def outbox(organization_id:uuid.UUID,authenticated:Annotated[AuthenticatedUser,Depends(get_current_user)],session:Annotated[Session,Depends(get_session)],cursor:str|None=None,page_size:int=Query(50,ge=1,le=100)):return collection(OutboxEvent,organization_id,authenticated,session,cursor,page_size,True)
@router.get("/audit-logs")
def audits(organization_id:uuid.UUID,authenticated:Annotated[AuthenticatedUser,Depends(get_current_user)],session:Annotated[Session,Depends(get_session)],cursor:str|None=None,page_size:int=Query(50,ge=1,le=100)):return collection(AuditLog,organization_id,authenticated,session,cursor,page_size,True)
