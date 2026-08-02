BEGIN;

-- Running upgrade 57d2abd856ae -> 0003_ai_storage_workflow

ALTER TABLE projects ADD COLUMN version INTEGER DEFAULT '1' NOT NULL;

ALTER TABLE artifacts ADD COLUMN version INTEGER DEFAULT '1' NOT NULL;

ALTER TABLE reviews ADD COLUMN version INTEGER DEFAULT '1' NOT NULL;

ALTER TABLE ai_runs ADD COLUMN billed_minutes INTEGER;

ALTER TABLE ai_runs ADD COLUMN minute_rate_snapshot NUMERIC(18, 8);

ALTER TABLE ai_runs ADD COLUMN input_rate_snapshot NUMERIC(18, 8);

ALTER TABLE ai_runs ADD COLUMN output_rate_snapshot NUMERIC(18, 8);

ALTER TABLE ai_runs ADD COLUMN calculated_cost NUMERIC(18, 8);

ALTER TABLE ai_runs ADD COLUMN version INTEGER DEFAULT '1' NOT NULL;

ALTER TABLE ai_runs ADD CONSTRAINT ck_ai_runs_billed_minutes CHECK (billed_minutes IS NULL OR billed_minutes >= 0);

ALTER TABLE ai_runs ADD CONSTRAINT ck_ai_runs_calculated_cost CHECK (calculated_cost IS NULL OR calculated_cost >= 0);

CREATE TABLE ai_settings (
    id UUID NOT NULL,
    organization_id UUID NOT NULL,
    project_id UUID,
    provider VARCHAR(30) NOT NULL,
    model VARCHAR(100) NOT NULL,
    operation_type VARCHAR(50) NOT NULL,
    enabled BOOLEAN NOT NULL,
    review_threshold INTEGER NOT NULL,
    max_auto_revision_count INTEGER NOT NULL,
    minute_rate NUMERIC(18, 8) NOT NULL,
    token_input_rate NUMERIC(18, 8) NOT NULL,
    token_output_rate NUMERIC(18, 8) NOT NULL,
    currency VARCHAR(3) DEFAULT 'JPY' NOT NULL,
    version INTEGER DEFAULT '1' NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY(organization_id) REFERENCES organizations (id) ON DELETE RESTRICT,
    FOREIGN KEY(project_id) REFERENCES projects (id) ON DELETE RESTRICT,
    CONSTRAINT ck_ai_settings_provider CHECK (provider IN ('openai','anthropic')),
    CONSTRAINT ck_ai_settings_operation CHECK (operation_type IN ('hearing','estimate','document_generation','code_generation','review','revision','test_generation','deployment_analysis')),
    CONSTRAINT ck_ai_settings_threshold CHECK (review_threshold BETWEEN 0 AND 100),
    CONSTRAINT ck_ai_settings_revisions CHECK (max_auto_revision_count BETWEEN 0 AND 10),
    CONSTRAINT ck_ai_settings_rates CHECK (minute_rate >= 0 AND token_input_rate >= 0 AND token_output_rate >= 0),
    CONSTRAINT ck_ai_settings_currency CHECK (currency = upper(currency) AND length(currency) = 3)
);

CREATE INDEX ix_ai_settings_resolution ON ai_settings (organization_id, project_id, provider, model, operation_type);

CREATE UNIQUE INDEX uq_ai_settings_project_scope ON ai_settings (organization_id, project_id, provider, model, operation_type) WHERE project_id IS NOT NULL;

CREATE UNIQUE INDEX uq_ai_settings_organization_scope ON ai_settings (organization_id, provider, model, operation_type) WHERE project_id IS NULL;

CREATE TABLE workflow_jobs (
    id UUID NOT NULL,
    organization_id UUID NOT NULL,
    project_id UUID NOT NULL,
    job_type VARCHAR(50) NOT NULL,
    status VARCHAR(30) NOT NULL,
    attempt_count INTEGER NOT NULL,
    max_attempts INTEGER NOT NULL,
    locked_at TIMESTAMP WITH TIME ZONE,
    locked_by VARCHAR(100),
    last_error_code VARCHAR(100),
    version INTEGER DEFAULT '1' NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY(organization_id) REFERENCES organizations (id) ON DELETE RESTRICT,
    FOREIGN KEY(project_id) REFERENCES projects (id) ON DELETE RESTRICT,
    CONSTRAINT ck_workflow_jobs_type CHECK (job_type IN ('auto_revision')),
    CONSTRAINT ck_workflow_jobs_status CHECK (status IN ('pending','running','completed','escalated','failed')),
    CONSTRAINT ck_workflow_jobs_attempts CHECK (attempt_count >= 0 AND max_attempts BETWEEN 0 AND 10)
);

CREATE INDEX ix_workflow_jobs_claim ON workflow_jobs (status, locked_at);

CREATE INDEX ix_workflow_jobs_project_created ON workflow_jobs (project_id, created_at);

CREATE TABLE artifact_upload_intents (
    id UUID NOT NULL,
    version_id UUID NOT NULL,
    organization_id UUID NOT NULL,
    project_id UUID NOT NULL,
    artifact_id UUID NOT NULL,
    storage_key VARCHAR(1024) NOT NULL,
    mime_type VARCHAR(255) NOT NULL,
    expected_size INTEGER NOT NULL,
    expected_hash VARCHAR(64) NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_by_user_id UUID NOT NULL,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (id),
    UNIQUE (version_id),
    UNIQUE (storage_key),
    FOREIGN KEY(organization_id) REFERENCES organizations (id) ON DELETE RESTRICT,
    FOREIGN KEY(project_id) REFERENCES projects (id) ON DELETE RESTRICT,
    FOREIGN KEY(artifact_id) REFERENCES artifacts (id) ON DELETE RESTRICT,
    FOREIGN KEY(created_by_user_id) REFERENCES users (id) ON DELETE RESTRICT,
    CONSTRAINT ck_upload_intents_size CHECK (expected_size >= 0),
    CONSTRAINT ck_upload_intents_status CHECK (status IN ('pending','completed','expired','cancelled'))
);

CREATE INDEX ix_upload_intents_artifact_status ON artifact_upload_intents (artifact_id, status);

UPDATE alembic_version SET version_num='0003_ai_storage_workflow' WHERE alembic_version.version_num = '57d2abd856ae';

COMMIT;
