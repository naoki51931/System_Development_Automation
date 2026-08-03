import uuid
from typing import Annotated
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.api.pagination import paginate_query
from app.auth.dependencies import AuthenticatedUser, get_current_user, get_session, require_organization_access
from app.models import AISetting, Artifact, ArtifactVersion, AuditLog, ChangeRequest, ChatRoom, Contract, DocumentGenerationJob, EmailMessage, MaintenanceContract, Notification, OutboxEvent, PaymentIntent, Project, Review, ReviewComment, WorkflowJob
router=APIRouter(prefix="/api/v1",tags=["cursor-collections"])

def simple(x):
    fields=("id","organization_id","project_id","status","created_at","event_type","job_type","artifact_type","title","review_type","score","attempt_count","max_attempts","last_error_code","version","name","project_code","current_phase","estimate_number","contract_number","total_amount","currency","terms_version","provider","model","operation_type","review_threshold","max_auto_revision_count","message_type","body","severity","read_at","valid_until","quality_score","artifact_id","artifact_version_id","review_id","contract_id","estimate_id","maintenance_contract_id","chat_room_id","chat_message_id","amount","subtotal","tax_amount","enabled","roles","display_name","email","membership_id","deduplication_key","dead_lettered_at")
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

@router.get("/dashboard")
def dashboard(organization_id:uuid.UUID,authenticated:Annotated[AuthenticatedUser,Depends(get_current_user)],session:Annotated[Session,Depends(get_session)]):
    require_organization_access(organization_id,authenticated,session)
    def count(model,*where): return session.scalar(select(func.count()).select_from(model).where(model.organization_id==organization_id,*where)) or 0
    latest=session.scalar(select(Artifact).where(Artifact.organization_id==organization_id).order_by(Artifact.updated_at.desc(),Artifact.id.desc()).limit(1))
    return {"active_projects":count(Project,Project.status.notin_(["closed","suspended"])),"review_waiting":count(Review,Review.status.in_(["pending","in_progress"])),"unread_notifications":count(Notification,Notification.user_id==authenticated.user.id,Notification.status.in_(["pending","delivered"])),"latest_artifact":simple(latest) if latest else None,"maintenance_active":count(MaintenanceContract,MaintenanceContract.status=="active"),"payment_pending":count(PaymentIntent,PaymentIntent.status.in_(["requires_payment_method","requires_confirmation","processing"]))}

@router.get("/contracts")
def contracts(organization_id:uuid.UUID,authenticated:Annotated[AuthenticatedUser,Depends(get_current_user)],session:Annotated[Session,Depends(get_session)],cursor:str|None=None,page_size:int=Query(50,ge=1,le=100)):return collection(Contract,organization_id,authenticated,session,cursor,page_size)
@router.get("/payment-intents")
def payments(organization_id:uuid.UUID,authenticated:Annotated[AuthenticatedUser,Depends(get_current_user)],session:Annotated[Session,Depends(get_session)],cursor:str|None=None,page_size:int=Query(50,ge=1,le=100)):return collection(PaymentIntent,organization_id,authenticated,session,cursor,page_size)
@router.get("/maintenance-contracts")
def maintenance(organization_id:uuid.UUID,authenticated:Annotated[AuthenticatedUser,Depends(get_current_user)],session:Annotated[Session,Depends(get_session)],cursor:str|None=None,page_size:int=Query(50,ge=1,le=100)):return collection(MaintenanceContract,organization_id,authenticated,session,cursor,page_size)
@router.get("/artifact-versions")
def versions(organization_id:uuid.UUID,authenticated:Annotated[AuthenticatedUser,Depends(get_current_user)],session:Annotated[Session,Depends(get_session)],cursor:str|None=None,page_size:int=Query(50,ge=1,le=100)):
    require_organization_access(organization_id,authenticated,session)
    statement=select(ArtifactVersion).join(Artifact,Artifact.id==ArtifactVersion.artifact_id).where(Artifact.organization_id==organization_id)
    return paginate_query(session,statement,ArtifactVersion,cursor,page_size,simple)
@router.get("/review-comments")
def comments(organization_id:uuid.UUID,authenticated:Annotated[AuthenticatedUser,Depends(get_current_user)],session:Annotated[Session,Depends(get_session)],cursor:str|None=None,page_size:int=Query(50,ge=1,le=100)):
    require_organization_access(organization_id,authenticated,session)
    statement=select(ReviewComment).join(Review,Review.id==ReviewComment.review_id).where(Review.organization_id==organization_id)
    return paginate_query(session,statement,ReviewComment,cursor,page_size,simple)
@router.get("/change-requests")
def changes(organization_id:uuid.UUID,authenticated:Annotated[AuthenticatedUser,Depends(get_current_user)],session:Annotated[Session,Depends(get_session)],cursor:str|None=None,page_size:int=Query(50,ge=1,le=100)):return collection(ChangeRequest,organization_id,authenticated,session,cursor,page_size)
@router.get("/ai-settings")
def settings(organization_id:uuid.UUID,authenticated:Annotated[AuthenticatedUser,Depends(get_current_user)],session:Annotated[Session,Depends(get_session)],cursor:str|None=None,page_size:int=Query(50,ge=1,le=100)):return collection(AISetting,organization_id,authenticated,session,cursor,page_size,True)
