import uuid

from pydantic import BaseModel, Field


class ProjectCreate(BaseModel):
    organization_id: uuid.UUID
    project_code: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    customer_user_id: uuid.UUID | None = None
    project_manager_user_id: uuid.UUID | None = None


class ArtifactCreate(BaseModel):
    artifact_type: str
    title: str = Field(min_length=1, max_length=255)


class ArtifactVersionCreate(BaseModel):
    storage_key: str = Field(min_length=1, max_length=1024)
    content_hash: str = Field(min_length=16, max_length=128)
    mime_type: str = Field(min_length=1, max_length=255)
    file_size: int = Field(ge=0)
    generated_by: str
    ai_run_id: uuid.UUID | None = None
    change_summary: str | None = None


class ReviewCreate(BaseModel):
    review_type: str
    reviewer_user_id: uuid.UUID | None = None
    ai_run_id: uuid.UUID | None = None
    status: str = "pending"
    score: int | None = Field(default=None, ge=0, le=100)
    summary: str | None = None


class ReviewCommentCreate(BaseModel):
    author_user_id: uuid.UUID | None = None
    comment_type: str = "finding"
    severity: str
    body: str = Field(min_length=1)
    target_path: str | None = None
    target_line: int | None = Field(default=None, gt=0)


class DecisionRequest(BaseModel):
    comment: str | None = None
