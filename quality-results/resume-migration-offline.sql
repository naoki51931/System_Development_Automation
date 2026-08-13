BEGIN;

CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL,
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

-- Running upgrade  -> 0001_migration_baseline

INSERT INTO alembic_version (version_num) VALUES ('0001_migration_baseline') RETURNING alembic_version.version_num;

-- Running upgrade 0001_migration_baseline -> 0002_identity_access

CREATE TABLE organizations (
    id UUID NOT NULL,
    name VARCHAR(255) NOT NULL,
    status VARCHAR(30) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (id)
);

CREATE INDEX ix_organizations_status ON organizations (status);

CREATE TABLE users (
    id UUID NOT NULL,
    cognito_sub VARCHAR(255) NOT NULL,
    email VARCHAR(320) NOT NULL,
    display_name VARCHAR(100) NOT NULL,
    status VARCHAR(30) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT ck_users_email_lowercase CHECK (email = lower(email)),
    CONSTRAINT uq_users_cognito_sub UNIQUE (cognito_sub),
    CONSTRAINT uq_users_email UNIQUE (email)
);

CREATE INDEX ix_users_status ON users (status);

CREATE TABLE roles (
    id UUID NOT NULL,
    code VARCHAR(50) NOT NULL,
    display_name VARCHAR(100) NOT NULL,
    description TEXT,
    is_system BOOLEAN NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uq_roles_code UNIQUE (code)
);

CREATE TABLE organization_memberships (
    id UUID NOT NULL,
    organization_id UUID NOT NULL,
    user_id UUID NOT NULL,
    status VARCHAR(30) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY(organization_id) REFERENCES organizations (id) ON DELETE RESTRICT,
    FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE RESTRICT,
    CONSTRAINT uq_memberships_organization_user UNIQUE (organization_id, user_id)
);

CREATE INDEX ix_memberships_user_status ON organization_memberships (user_id, status);

CREATE INDEX ix_memberships_organization_status ON organization_memberships (organization_id, status);

CREATE TABLE membership_roles (
    membership_id UUID NOT NULL,
    role_id UUID NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (membership_id, role_id),
    FOREIGN KEY(membership_id) REFERENCES organization_memberships (id) ON DELETE CASCADE,
    FOREIGN KEY(role_id) REFERENCES roles (id) ON DELETE RESTRICT
);

CREATE INDEX ix_membership_roles_role_id ON membership_roles (role_id);

CREATE TABLE audit_logs (
    id UUID NOT NULL,
    organization_id UUID NOT NULL,
    actor_user_id UUID,
    action VARCHAR(100) NOT NULL,
    resource_type VARCHAR(100) NOT NULL,
    resource_id UUID,
    before_json JSONB,
    after_json JSONB,
    ip_address INET,
    request_id UUID NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY(organization_id) REFERENCES organizations (id) ON DELETE RESTRICT,
    FOREIGN KEY(actor_user_id) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_audit_logs_organization_created ON audit_logs (organization_id, created_at DESC);

CREATE INDEX ix_audit_logs_request_id ON audit_logs (request_id);

CREATE FUNCTION prevent_audit_log_mutation() RETURNS trigger AS $$
        BEGIN
          RAISE EXCEPTION 'audit_logs are append-only';
        END;
        $$ LANGUAGE plpgsql;
        CREATE TRIGGER audit_logs_append_only
        BEFORE UPDATE OR DELETE ON audit_logs
        FOR EACH ROW EXECUTE FUNCTION prevent_audit_log_mutation();;

UPDATE alembic_version SET version_num='0002_identity_access' WHERE alembic_version.version_num = '0001_migration_baseline';

-- Running upgrade 0002_identity_access -> 57d2abd856ae

CREATE TABLE projects (
    id UUID NOT NULL,
    organization_id UUID NOT NULL,
    project_code VARCHAR(50) NOT NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    status VARCHAR(30) NOT NULL,
    current_phase VARCHAR(30) NOT NULL,
    customer_user_id UUID,
    project_manager_user_id UUID,
    archived_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT ck_projects_phase CHECK (current_phase IN ('hearing', 'estimate', 'requirements', 'basic_design', 'detailed_design', 'development', 'testing', 'staging', 'acceptance', 'production', 'maintenance')),
    CONSTRAINT ck_projects_status CHECK (status IN ('draft', 'hearing', 'estimating', 'awaiting_payment', 'requirements', 'basic_design', 'detailed_design', 'development', 'testing', 'staging', 'awaiting_acceptance', 'production', 'maintenance', 'suspended', 'closed')),
    FOREIGN KEY(customer_user_id) REFERENCES users (id) ON DELETE RESTRICT,
    FOREIGN KEY(organization_id) REFERENCES organizations (id) ON DELETE RESTRICT,
    FOREIGN KEY(project_manager_user_id) REFERENCES users (id) ON DELETE RESTRICT,
    CONSTRAINT uq_projects_organization_code UNIQUE (organization_id, project_code)
);

CREATE INDEX ix_projects_organization_status ON projects (organization_id, status);

CREATE INDEX ix_projects_organization_updated ON projects (organization_id, updated_at);

CREATE TABLE ai_runs (
    id UUID NOT NULL,
    organization_id UUID NOT NULL,
    project_id UUID NOT NULL,
    provider VARCHAR(30) NOT NULL,
    model VARCHAR(100) NOT NULL,
    operation_type VARCHAR(50) NOT NULL,
    status VARCHAR(30) NOT NULL,
    input_tokens INTEGER,
    output_tokens INTEGER,
    duration_ms INTEGER,
    estimated_cost NUMERIC(18, 8),
    request_hash VARCHAR(128),
    prompt_version VARCHAR(50),
    retry_count INTEGER NOT NULL,
    error_code VARCHAR(100),
    error_message_sanitized TEXT,
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT ck_ai_runs_operation CHECK (operation_type IN ('hearing', 'estimate', 'document_generation', 'code_generation', 'review', 'revision', 'test_generation', 'deployment_analysis')),
    CONSTRAINT ck_ai_runs_provider CHECK (provider IN ('openai', 'anthropic')),
    CONSTRAINT ck_ai_runs_cost CHECK (estimated_cost IS NULL OR estimated_cost >= 0),
    CONSTRAINT ck_ai_runs_retry_count CHECK (retry_count >= 0),
    FOREIGN KEY(organization_id) REFERENCES organizations (id) ON DELETE RESTRICT,
    FOREIGN KEY(project_id) REFERENCES projects (id) ON DELETE RESTRICT
);

CREATE INDEX ix_ai_runs_organization_status ON ai_runs (organization_id, status);

CREATE INDEX ix_ai_runs_project_created ON ai_runs (project_id, created_at);

CREATE TABLE artifacts (
    id UUID NOT NULL,
    organization_id UUID NOT NULL,
    project_id UUID NOT NULL,
    artifact_type VARCHAR(50) NOT NULL,
    title VARCHAR(255) NOT NULL,
    status VARCHAR(30) NOT NULL,
    current_version_id UUID,
    created_by_user_id UUID,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT ck_artifacts_type CHECK (artifact_type IN ('hearing_sheet', 'estimate', 'requirements_definition', 'basic_design', 'detailed_design', 'screen_design', 'api_specification', 'database_design', 'test_specification', 'test_report', 'operation_manual', 'release_procedure', 'source_code')),
    CONSTRAINT ck_artifacts_status CHECK (status IN ('draft', 'ai_reviewing', 'human_reviewing', 'revision_requested', 'approved', 'superseded')),
    FOREIGN KEY(created_by_user_id) REFERENCES users (id) ON DELETE SET NULL,
    FOREIGN KEY(organization_id) REFERENCES organizations (id) ON DELETE RESTRICT,
    FOREIGN KEY(project_id) REFERENCES projects (id) ON DELETE RESTRICT
);

CREATE INDEX ix_artifacts_organization_type ON artifacts (organization_id, artifact_type);

CREATE INDEX ix_artifacts_project_status ON artifacts (project_id, status);

CREATE TABLE project_members (
    id UUID NOT NULL,
    project_id UUID NOT NULL,
    user_id UUID NOT NULL,
    project_role VARCHAR(30) NOT NULL,
    status VARCHAR(30) NOT NULL,
    joined_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    left_at TIMESTAMP WITH TIME ZONE,
    PRIMARY KEY (id),
    CONSTRAINT ck_project_members_role CHECK (project_role IN ('project_owner', 'project_manager', 'reviewer', 'developer', 'customer', 'viewer')),
    CONSTRAINT ck_project_members_status CHECK (status IN ('active', 'inactive')),
    FOREIGN KEY(project_id) REFERENCES projects (id) ON DELETE RESTRICT,
    FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE RESTRICT,
    CONSTRAINT uq_project_members_project_user UNIQUE (project_id, user_id)
);

CREATE INDEX ix_project_members_user_status ON project_members (user_id, status);

CREATE TABLE artifact_versions (
    id UUID NOT NULL,
    artifact_id UUID NOT NULL,
    version_number INTEGER NOT NULL,
    storage_key VARCHAR(1024) NOT NULL,
    content_hash VARCHAR(128) NOT NULL,
    mime_type VARCHAR(255) NOT NULL,
    file_size INTEGER NOT NULL,
    generated_by VARCHAR(20) NOT NULL,
    ai_run_id UUID,
    change_summary TEXT,
    created_by_user_id UUID,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT ck_artifact_versions_ai_run CHECK ((generated_by = 'ai' AND ai_run_id IS NOT NULL) OR (generated_by = 'human' AND ai_run_id IS NULL)),
    CONSTRAINT ck_artifact_versions_generated_by CHECK (generated_by IN ('human', 'ai')),
    CONSTRAINT ck_artifact_versions_file_size CHECK (file_size >= 0),
    CONSTRAINT ck_artifact_versions_number CHECK (version_number > 0),
    FOREIGN KEY(ai_run_id) REFERENCES ai_runs (id) ON DELETE RESTRICT,
    FOREIGN KEY(artifact_id) REFERENCES artifacts (id) ON DELETE RESTRICT,
    FOREIGN KEY(created_by_user_id) REFERENCES users (id) ON DELETE SET NULL,
    CONSTRAINT uq_artifact_versions_number UNIQUE (artifact_id, version_number)
);

CREATE INDEX ix_artifact_versions_artifact_created ON artifact_versions (artifact_id, created_at);

CREATE INDEX ix_artifact_versions_content_hash ON artifact_versions (content_hash);

ALTER TABLE artifacts ADD CONSTRAINT fk_artifacts_current_version FOREIGN KEY(current_version_id) REFERENCES artifact_versions (id) ON DELETE RESTRICT;

CREATE TABLE approval_events (
    id UUID NOT NULL,
    organization_id UUID NOT NULL,
    project_id UUID NOT NULL,
    artifact_version_id UUID NOT NULL,
    actor_user_id UUID NOT NULL,
    action VARCHAR(30) NOT NULL,
    comment TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT ck_approval_events_action CHECK (action IN ('submitted','approved','rejected','changes_requested','resubmitted','customer_accepted')),
    FOREIGN KEY(actor_user_id) REFERENCES users (id) ON DELETE RESTRICT,
    FOREIGN KEY(artifact_version_id) REFERENCES artifact_versions (id) ON DELETE RESTRICT,
    FOREIGN KEY(organization_id) REFERENCES organizations (id) ON DELETE RESTRICT,
    FOREIGN KEY(project_id) REFERENCES projects (id) ON DELETE RESTRICT
);

CREATE INDEX ix_approval_events_project_created ON approval_events (project_id, created_at);

CREATE INDEX ix_approval_events_version_created ON approval_events (artifact_version_id, created_at);

CREATE TABLE reviews (
    id UUID NOT NULL,
    organization_id UUID NOT NULL,
    project_id UUID NOT NULL,
    artifact_version_id UUID NOT NULL,
    review_type VARCHAR(30) NOT NULL,
    reviewer_user_id UUID,
    ai_run_id UUID,
    status VARCHAR(30) NOT NULL,
    score INTEGER,
    summary TEXT,
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT ck_reviews_reviewer_source CHECK ((review_type = 'ai' AND ai_run_id IS NOT NULL AND reviewer_user_id IS NULL) OR (review_type <> 'ai' AND reviewer_user_id IS NOT NULL AND ai_run_id IS NULL)),
    CONSTRAINT ck_reviews_type CHECK (review_type IN ('ai', 'human', 'customer_acceptance', 'security', 'architecture', 'code_quality', 'test_quality')),
    CONSTRAINT ck_reviews_status CHECK (status IN ('pending', 'in_progress', 'passed', 'failed', 'changes_requested', 'cancelled')),
    CONSTRAINT ck_reviews_score CHECK (score IS NULL OR (score >= 0 AND score <= 100)),
    FOREIGN KEY(ai_run_id) REFERENCES ai_runs (id) ON DELETE RESTRICT,
    FOREIGN KEY(artifact_version_id) REFERENCES artifact_versions (id) ON DELETE RESTRICT,
    FOREIGN KEY(organization_id) REFERENCES organizations (id) ON DELETE RESTRICT,
    FOREIGN KEY(project_id) REFERENCES projects (id) ON DELETE RESTRICT,
    FOREIGN KEY(reviewer_user_id) REFERENCES users (id) ON DELETE RESTRICT
);

CREATE INDEX ix_reviews_project_created ON reviews (project_id, created_at);

CREATE INDEX ix_reviews_version_status ON reviews (artifact_version_id, status);

CREATE TABLE review_comments (
    id UUID NOT NULL,
    review_id UUID NOT NULL,
    author_user_id UUID,
    comment_type VARCHAR(30) NOT NULL,
    severity VARCHAR(20) NOT NULL,
    body TEXT NOT NULL,
    target_path VARCHAR(1024),
    target_line INTEGER,
    status VARCHAR(20) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    resolved_at TIMESTAMP WITH TIME ZONE,
    resolved_by_user_id UUID,
    PRIMARY KEY (id),
    CONSTRAINT ck_review_comments_severity CHECK (severity IN ('info', 'minor', 'major', 'critical')),
    CONSTRAINT ck_review_comments_status CHECK (status IN ('open', 'accepted', 'rejected', 'resolved')),
    CONSTRAINT ck_review_comments_body CHECK (length(trim(body)) > 0),
    CONSTRAINT ck_review_comments_target_line CHECK (target_line IS NULL OR target_line > 0),
    FOREIGN KEY(author_user_id) REFERENCES users (id) ON DELETE RESTRICT,
    FOREIGN KEY(resolved_by_user_id) REFERENCES users (id) ON DELETE RESTRICT,
    FOREIGN KEY(review_id) REFERENCES reviews (id) ON DELETE RESTRICT
);

CREATE INDEX ix_review_comments_review_status ON review_comments (review_id, status);

CREATE FUNCTION prevent_artifact_version_mutation() RETURNS trigger AS $$ BEGIN RAISE EXCEPTION 'artifact_versions are immutable'; END; $$ LANGUAGE plpgsql;
        CREATE TRIGGER artifact_versions_immutable BEFORE UPDATE OR DELETE ON artifact_versions FOR EACH ROW EXECUTE FUNCTION prevent_artifact_version_mutation();
        CREATE FUNCTION prevent_approval_event_mutation() RETURNS trigger AS $$ BEGIN RAISE EXCEPTION 'approval_events are append-only'; END; $$ LANGUAGE plpgsql;
        CREATE TRIGGER approval_events_append_only BEFORE UPDATE OR DELETE ON approval_events FOR EACH ROW EXECUTE FUNCTION prevent_approval_event_mutation();
        CREATE FUNCTION prevent_review_history_delete() RETURNS trigger AS $$ BEGIN RAISE EXCEPTION 'review history cannot be deleted'; END; $$ LANGUAGE plpgsql;
        CREATE TRIGGER reviews_no_delete BEFORE DELETE ON reviews FOR EACH ROW EXECUTE FUNCTION prevent_review_history_delete();
        CREATE TRIGGER review_comments_no_delete BEFORE DELETE ON review_comments FOR EACH ROW EXECUTE FUNCTION prevent_review_history_delete();;

UPDATE alembic_version SET version_num='57d2abd856ae' WHERE alembic_version.version_num = '0002_identity_access';

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

-- Running upgrade 0003_ai_storage_workflow -> 215db73ed802

CREATE TABLE maintenance_plans (
    id UUID NOT NULL,
    organization_id UUID,
    name VARCHAR(100) NOT NULL,
    code VARCHAR(50) NOT NULL,
    status VARCHAR(20) NOT NULL,
    currency VARCHAR(3) NOT NULL,
    monthly_price NUMERIC(18, 8) NOT NULL,
    included_ai_minutes INTEGER NOT NULL,
    included_human_minutes INTEGER NOT NULL,
    backup_retention_days INTEGER NOT NULL,
    support_response_hours INTEGER NOT NULL,
    monitoring_enabled BOOLEAN NOT NULL,
    staging_enabled BOOLEAN NOT NULL,
    version INTEGER NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY(organization_id) REFERENCES organizations (id) ON DELETE RESTRICT
);

CREATE UNIQUE INDEX uq_maintenance_plans_org_code ON maintenance_plans (organization_id, code) WHERE organization_id IS NOT NULL;

CREATE UNIQUE INDEX uq_maintenance_plans_system_code ON maintenance_plans (code) WHERE organization_id IS NULL;

CREATE TABLE payment_customers (
    id UUID NOT NULL,
    organization_id UUID NOT NULL,
    provider VARCHAR(20) NOT NULL,
    provider_customer_id VARCHAR(255) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY(organization_id) REFERENCES organizations (id) ON DELETE RESTRICT,
    CONSTRAINT uq_payment_customers_org_provider UNIQUE (organization_id, provider),
    CONSTRAINT uq_payment_customers_provider_id UNIQUE (provider, provider_customer_id)
);

CREATE TABLE payment_events (
    id UUID NOT NULL,
    organization_id UUID NOT NULL,
    provider VARCHAR(20) NOT NULL,
    provider_event_id VARCHAR(255) NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    status VARCHAR(30) NOT NULL,
    payload_hash VARCHAR(64) NOT NULL,
    received_at TIMESTAMP WITH TIME ZONE NOT NULL,
    processed_at TIMESTAMP WITH TIME ZONE,
    failure_code VARCHAR(100),
    retry_count INTEGER NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY(organization_id) REFERENCES organizations (id) ON DELETE RESTRICT,
    CONSTRAINT uq_payment_events_provider_event UNIQUE (provider, provider_event_id)
);

CREATE INDEX ix_payment_events_status_received ON payment_events (status, received_at);

CREATE TABLE pricing_rules (
    id UUID NOT NULL,
    organization_id UUID,
    artifact_type VARCHAR(50) NOT NULL,
    base_price NUMERIC(18, 8) NOT NULL,
    complexity_multiplier NUMERIC(18, 8) NOT NULL,
    quality_multiplier NUMERIC(18, 8) NOT NULL,
    currency VARCHAR(3) NOT NULL,
    enabled BOOLEAN NOT NULL,
    version INTEGER NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT ck_pricing_rules_values CHECK (base_price >= 0 AND complexity_multiplier >= 0 AND quality_multiplier >= 0),
    FOREIGN KEY(organization_id) REFERENCES organizations (id) ON DELETE RESTRICT
);

CREATE INDEX ix_pricing_rules_resolution ON pricing_rules (organization_id, artifact_type, enabled);

CREATE UNIQUE INDEX uq_pricing_rules_system_type ON pricing_rules (artifact_type) WHERE organization_id IS NULL;

CREATE UNIQUE INDEX uq_pricing_rules_org_type ON pricing_rules (organization_id, artifact_type) WHERE organization_id IS NOT NULL;

CREATE TABLE estimates (
    id UUID NOT NULL,
    organization_id UUID NOT NULL,
    project_id UUID NOT NULL,
    estimate_number VARCHAR(50) NOT NULL,
    status VARCHAR(30) NOT NULL,
    currency VARCHAR(3) NOT NULL,
    subtotal NUMERIC(18, 8) NOT NULL,
    tax_amount NUMERIC(18, 8) NOT NULL,
    total_amount NUMERIC(18, 8) NOT NULL,
    valid_until DATE NOT NULL,
    version INTEGER NOT NULL,
    created_by_user_id UUID NOT NULL,
    approved_by_user_id UUID,
    approved_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT ck_estimates_status CHECK (status IN ('draft','calculating','internal_review','customer_review','approved','rejected','expired','superseded')),
    CONSTRAINT ck_estimates_currency CHECK (currency = upper(currency) AND length(currency) = 3),
    CONSTRAINT ck_estimates_amounts CHECK (subtotal >= 0 AND tax_amount >= 0 AND total_amount >= 0),
    CONSTRAINT ck_estimates_total CHECK (total_amount = subtotal + tax_amount),
    FOREIGN KEY(approved_by_user_id) REFERENCES users (id) ON DELETE RESTRICT,
    FOREIGN KEY(created_by_user_id) REFERENCES users (id) ON DELETE RESTRICT,
    FOREIGN KEY(organization_id) REFERENCES organizations (id) ON DELETE RESTRICT,
    FOREIGN KEY(project_id) REFERENCES projects (id) ON DELETE RESTRICT,
    CONSTRAINT uq_estimates_organization_number UNIQUE (organization_id, estimate_number)
);

CREATE INDEX ix_estimates_project_status ON estimates (project_id, status);

CREATE TABLE payment_methods (
    id UUID NOT NULL,
    organization_id UUID NOT NULL,
    payment_customer_id UUID NOT NULL,
    provider VARCHAR(20) NOT NULL,
    provider_payment_method_id VARCHAR(255) NOT NULL,
    brand VARCHAR(30),
    last4 VARCHAR(4),
    expiry_month INTEGER,
    expiry_year INTEGER,
    status VARCHAR(20) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT ck_payment_methods_last4 CHECK (last4 IS NULL OR last4 ~ '^[0-9]{4}$'),
    CONSTRAINT ck_payment_methods_expiry_month CHECK (expiry_month IS NULL OR expiry_month BETWEEN 1 AND 12),
    FOREIGN KEY(organization_id) REFERENCES organizations (id) ON DELETE RESTRICT,
    FOREIGN KEY(payment_customer_id) REFERENCES payment_customers (id) ON DELETE RESTRICT,
    CONSTRAINT uq_payment_methods_provider_id UNIQUE (provider, provider_payment_method_id)
);

CREATE TABLE estimate_items (
    id UUID NOT NULL,
    estimate_id UUID NOT NULL,
    item_type VARCHAR(30) NOT NULL,
    phase VARCHAR(50),
    description VARCHAR(500) NOT NULL,
    quantity NUMERIC(18, 8) NOT NULL,
    unit VARCHAR(30) NOT NULL,
    unit_price NUMERIC(18, 8) NOT NULL,
    amount NUMERIC(18, 8) NOT NULL,
    source_type VARCHAR(30) NOT NULL,
    source_reference_id UUID,
    display_order INTEGER NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT ck_estimate_items_nonnegative CHECK ((item_type = 'discount') OR (unit_price >= 0 AND amount >= 0)),
    CONSTRAINT ck_estimate_items_type CHECK (item_type IN ('ai_runtime','artifact_value','human_review','cloud','maintenance','option','discount','tax')),
    CONSTRAINT ck_estimate_items_source CHECK (source_type IN ('ai_run','artifact','manual','pricing_rule','cloud_estimate')),
    CONSTRAINT ck_estimate_items_quantity CHECK (quantity >= 0),
    CONSTRAINT ck_estimate_items_calculated_amount CHECK (amount = round(quantity * unit_price, 8)),
    FOREIGN KEY(estimate_id) REFERENCES estimates (id) ON DELETE RESTRICT,
    CONSTRAINT uq_estimate_items_order UNIQUE (estimate_id, display_order)
);

CREATE INDEX ix_estimate_items_estimate ON estimate_items (estimate_id);

CREATE TABLE artifact_pricing_snapshots (
    id UUID NOT NULL,
    estimate_item_id UUID NOT NULL,
    artifact_id UUID NOT NULL,
    pricing_rule_id UUID,
    artifact_type VARCHAR(50) NOT NULL,
    base_price NUMERIC(18, 8) NOT NULL,
    complexity_multiplier NUMERIC(18, 8) NOT NULL,
    quality_multiplier NUMERIC(18, 8) NOT NULL,
    screen_count INTEGER NOT NULL,
    api_count INTEGER NOT NULL,
    table_count INTEGER NOT NULL,
    test_case_count INTEGER NOT NULL,
    calculated_value NUMERIC(18, 8) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT ck_artifact_pricing_counts CHECK (screen_count >= 0 AND api_count >= 0 AND table_count >= 0 AND test_case_count >= 0),
    FOREIGN KEY(artifact_id) REFERENCES artifacts (id) ON DELETE RESTRICT,
    FOREIGN KEY(estimate_item_id) REFERENCES estimate_items (id) ON DELETE RESTRICT,
    FOREIGN KEY(pricing_rule_id) REFERENCES pricing_rules (id) ON DELETE RESTRICT,
    UNIQUE (estimate_item_id)
);

CREATE TABLE contracts (
    id UUID NOT NULL,
    organization_id UUID NOT NULL,
    project_id UUID NOT NULL,
    estimate_id UUID NOT NULL,
    contract_number VARCHAR(50) NOT NULL,
    status VARCHAR(30) NOT NULL,
    contract_type VARCHAR(30) NOT NULL,
    customer_accepted_by_user_id UUID,
    customer_accepted_at TIMESTAMP WITH TIME ZONE,
    provider_accepted_by_user_id UUID,
    provider_accepted_at TIMESTAMP WITH TIME ZONE,
    started_at TIMESTAMP WITH TIME ZONE,
    ended_at TIMESTAMP WITH TIME ZONE,
    terms_version VARCHAR(50) NOT NULL,
    document_artifact_version_id UUID,
    version INTEGER NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT ck_contracts_type CHECK (contract_type IN ('development','maintenance','additional_work')),
    CONSTRAINT ck_contracts_status CHECK (status IN ('draft','awaiting_customer','awaiting_provider','active','suspended','terminated','completed')),
    FOREIGN KEY(customer_accepted_by_user_id) REFERENCES users (id) ON DELETE RESTRICT,
    FOREIGN KEY(document_artifact_version_id) REFERENCES artifact_versions (id) ON DELETE RESTRICT,
    FOREIGN KEY(estimate_id) REFERENCES estimates (id) ON DELETE RESTRICT,
    FOREIGN KEY(organization_id) REFERENCES organizations (id) ON DELETE RESTRICT,
    FOREIGN KEY(project_id) REFERENCES projects (id) ON DELETE RESTRICT,
    FOREIGN KEY(provider_accepted_by_user_id) REFERENCES users (id) ON DELETE RESTRICT,
    CONSTRAINT uq_contracts_estimate UNIQUE (estimate_id),
    CONSTRAINT uq_contracts_organization_number UNIQUE (organization_id, contract_number)
);

CREATE INDEX ix_contracts_project_status ON contracts (project_id, status);

CREATE TABLE maintenance_contracts (
    id UUID NOT NULL,
    organization_id UUID NOT NULL,
    project_id UUID NOT NULL,
    contract_id UUID NOT NULL,
    maintenance_plan_id UUID NOT NULL,
    status VARCHAR(30) NOT NULL,
    started_at TIMESTAMP WITH TIME ZONE,
    current_period_start TIMESTAMP WITH TIME ZONE,
    current_period_end TIMESTAMP WITH TIME ZONE,
    grace_period_started_at TIMESTAMP WITH TIME ZONE,
    suspended_at TIMESTAMP WITH TIME ZONE,
    deletion_scheduled_at TIMESTAMP WITH TIME ZONE,
    terminated_at TIMESTAMP WITH TIME ZONE,
    provider_subscription_id VARCHAR(255),
    version INTEGER NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT ck_maintenance_contracts_status CHECK (status IN ('pending','active','past_due','grace_period','suspended','deletion_scheduled','terminated')),
    FOREIGN KEY(contract_id) REFERENCES contracts (id) ON DELETE RESTRICT,
    FOREIGN KEY(maintenance_plan_id) REFERENCES maintenance_plans (id) ON DELETE RESTRICT,
    FOREIGN KEY(organization_id) REFERENCES organizations (id) ON DELETE RESTRICT,
    FOREIGN KEY(project_id) REFERENCES projects (id) ON DELETE RESTRICT,
    CONSTRAINT uq_maintenance_contracts_contract UNIQUE (contract_id)
);

CREATE INDEX ix_maintenance_contracts_project_status ON maintenance_contracts (project_id, status);

CREATE TABLE payment_intents (
    id UUID NOT NULL,
    organization_id UUID NOT NULL,
    project_id UUID NOT NULL,
    contract_id UUID NOT NULL,
    provider VARCHAR(20) NOT NULL,
    provider_payment_intent_id VARCHAR(255) NOT NULL,
    status VARCHAR(30) NOT NULL,
    currency VARCHAR(3) NOT NULL,
    amount NUMERIC(18, 8) NOT NULL,
    idempotency_key VARCHAR(255) NOT NULL,
    failure_code VARCHAR(100),
    failure_message_sanitized TEXT,
    confirmed_at TIMESTAMP WITH TIME ZONE,
    version INTEGER NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT ck_payment_intents_status CHECK (status IN ('requires_payment_method','requires_confirmation','processing','succeeded','failed','cancelled','refunded')),
    CONSTRAINT ck_payment_intents_amount CHECK (amount >= 0),
    FOREIGN KEY(contract_id) REFERENCES contracts (id) ON DELETE RESTRICT,
    FOREIGN KEY(organization_id) REFERENCES organizations (id) ON DELETE RESTRICT,
    FOREIGN KEY(project_id) REFERENCES projects (id) ON DELETE RESTRICT,
    CONSTRAINT uq_payment_intents_idempotency UNIQUE (organization_id, provider, idempotency_key),
    CONSTRAINT uq_payment_intents_provider_id UNIQUE (provider, provider_payment_intent_id)
);

CREATE INDEX ix_payment_intents_contract_status ON payment_intents (contract_id, status);

CREATE TABLE maintenance_status_events (
    id UUID NOT NULL,
    organization_id UUID NOT NULL,
    project_id UUID NOT NULL,
    maintenance_contract_id UUID NOT NULL,
    from_status VARCHAR(30),
    to_status VARCHAR(30) NOT NULL,
    reason_code VARCHAR(100) NOT NULL,
    effective_at TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY(maintenance_contract_id) REFERENCES maintenance_contracts (id) ON DELETE RESTRICT,
    FOREIGN KEY(organization_id) REFERENCES organizations (id) ON DELETE RESTRICT,
    FOREIGN KEY(project_id) REFERENCES projects (id) ON DELETE RESTRICT
);

CREATE INDEX ix_maintenance_events_contract_effective ON maintenance_status_events (maintenance_contract_id, effective_at);

CREATE TABLE resource_deletion_requests (
    id UUID NOT NULL,
    organization_id UUID NOT NULL,
    project_id UUID NOT NULL,
    maintenance_contract_id UUID NOT NULL,
    status VARCHAR(30) NOT NULL,
    reason TEXT NOT NULL,
    scheduled_for TIMESTAMP WITH TIME ZONE NOT NULL,
    requested_by UUID,
    approved_by_first UUID,
    approved_by_second UUID,
    approved_at_first TIMESTAMP WITH TIME ZONE,
    approved_at_second TIMESTAMP WITH TIME ZONE,
    execution_reference VARCHAR(255),
    version INTEGER NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT ck_resource_deletion_requests_status CHECK (status IN ('draft','pending_first_approval','pending_second_approval','approved','cancelled','executed','failed')),
    CONSTRAINT ck_resource_deletion_two_approvers CHECK (approved_by_first IS NULL OR approved_by_second IS NULL OR approved_by_first <> approved_by_second),
    FOREIGN KEY(approved_by_first) REFERENCES users (id) ON DELETE RESTRICT,
    FOREIGN KEY(approved_by_second) REFERENCES users (id) ON DELETE RESTRICT,
    FOREIGN KEY(maintenance_contract_id) REFERENCES maintenance_contracts (id) ON DELETE RESTRICT,
    FOREIGN KEY(organization_id) REFERENCES organizations (id) ON DELETE RESTRICT,
    FOREIGN KEY(project_id) REFERENCES projects (id) ON DELETE RESTRICT,
    FOREIGN KEY(requested_by) REFERENCES users (id) ON DELETE RESTRICT
);

CREATE INDEX ix_deletion_requests_contract_status ON resource_deletion_requests (maintenance_contract_id, status);

CREATE TABLE subscriptions (
    id UUID NOT NULL,
    organization_id UUID NOT NULL,
    project_id UUID NOT NULL,
    maintenance_contract_id UUID NOT NULL,
    provider VARCHAR(20) NOT NULL,
    provider_subscription_id VARCHAR(255) NOT NULL,
    status VARCHAR(30) NOT NULL,
    current_period_start TIMESTAMP WITH TIME ZONE NOT NULL,
    current_period_end TIMESTAMP WITH TIME ZONE NOT NULL,
    version INTEGER NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY(maintenance_contract_id) REFERENCES maintenance_contracts (id) ON DELETE RESTRICT,
    FOREIGN KEY(organization_id) REFERENCES organizations (id) ON DELETE RESTRICT,
    FOREIGN KEY(project_id) REFERENCES projects (id) ON DELETE RESTRICT,
    CONSTRAINT uq_subscriptions_provider_id UNIQUE (provider, provider_subscription_id)
);

CREATE TABLE subscription_invoices (
    id UUID NOT NULL,
    organization_id UUID NOT NULL,
    project_id UUID NOT NULL,
    subscription_id UUID NOT NULL,
    provider_invoice_id VARCHAR(255) NOT NULL,
    status VARCHAR(30) NOT NULL,
    currency VARCHAR(3) NOT NULL,
    amount_due NUMERIC(18, 8) NOT NULL,
    attempt_count INTEGER NOT NULL,
    due_at TIMESTAMP WITH TIME ZONE NOT NULL,
    paid_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY(organization_id) REFERENCES organizations (id) ON DELETE RESTRICT,
    FOREIGN KEY(project_id) REFERENCES projects (id) ON DELETE RESTRICT,
    FOREIGN KEY(subscription_id) REFERENCES subscriptions (id) ON DELETE RESTRICT,
    UNIQUE (provider_invoice_id)
);

CREATE FUNCTION prevent_approved_estimate_mutation() RETURNS trigger AS $$
        BEGIN
            IF (TG_OP = 'UPDATE' AND OLD.status = 'approved') THEN
                RAISE EXCEPTION 'approved estimates are immutable';
            END IF;
            RETURN NEW;
        END; $$ LANGUAGE plpgsql;
        CREATE TRIGGER approved_estimates_immutable BEFORE UPDATE ON estimates FOR EACH ROW EXECUTE FUNCTION prevent_approved_estimate_mutation();
        CREATE FUNCTION prevent_approved_estimate_item_mutation() RETURNS trigger AS $$
        BEGIN
            IF EXISTS (SELECT 1 FROM estimates WHERE id = COALESCE(NEW.estimate_id, OLD.estimate_id) AND status = 'approved') THEN
                RAISE EXCEPTION 'approved estimate items are immutable';
            END IF;
            RETURN COALESCE(NEW, OLD);
        END; $$ LANGUAGE plpgsql;
        CREATE TRIGGER approved_estimate_items_immutable BEFORE INSERT OR UPDATE OR DELETE ON estimate_items FOR EACH ROW EXECUTE FUNCTION prevent_approved_estimate_item_mutation();
        CREATE FUNCTION prevent_billing_event_mutation() RETURNS trigger AS $$ BEGIN RAISE EXCEPTION 'billing events are append-only'; END; $$ LANGUAGE plpgsql;
        CREATE TRIGGER payment_events_append_only BEFORE UPDATE OR DELETE ON payment_events FOR EACH ROW EXECUTE FUNCTION prevent_billing_event_mutation();
        CREATE TRIGGER maintenance_status_events_append_only BEFORE UPDATE OR DELETE ON maintenance_status_events FOR EACH ROW EXECUTE FUNCTION prevent_billing_event_mutation();;

UPDATE alembic_version SET version_num='215db73ed802' WHERE alembic_version.version_num = '0003_ai_storage_workflow';

-- Running upgrade 215db73ed802 -> d8685773bc4a

CREATE TABLE document_templates (
    id UUID NOT NULL,
    organization_id UUID,
    template_code VARCHAR(100) NOT NULL,
    name VARCHAR(255) NOT NULL,
    document_type VARCHAR(50) NOT NULL,
    format VARCHAR(20) NOT NULL,
    locale VARCHAR(20) NOT NULL,
    status VARCHAR(20) NOT NULL,
    version_number INTEGER NOT NULL,
    template_storage_key VARCHAR(1024) NOT NULL,
    schema_version VARCHAR(50) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT ck_document_templates_format CHECK (format IN ('html','docx','xlsx','markdown')),
    CONSTRAINT ck_document_templates_status CHECK (status IN ('draft','approved','retired')),
    FOREIGN KEY(organization_id) REFERENCES organizations (id) ON DELETE RESTRICT
);

CREATE INDEX ix_document_templates_resolution ON document_templates (organization_id, document_type, locale, status, version_number);

CREATE UNIQUE INDEX uq_document_templates_org_version ON document_templates (organization_id, template_code, locale, version_number) WHERE organization_id IS NOT NULL;

CREATE UNIQUE INDEX uq_document_templates_system_version ON document_templates (template_code, locale, version_number) WHERE organization_id IS NULL;

CREATE TABLE email_templates (
    id UUID NOT NULL,
    organization_id UUID,
    template_code VARCHAR(100) NOT NULL,
    name VARCHAR(255) NOT NULL,
    subject_template VARCHAR(500) NOT NULL,
    body_text_template TEXT NOT NULL,
    body_html_template TEXT,
    locale VARCHAR(20) NOT NULL,
    status VARCHAR(20) NOT NULL,
    version_number INTEGER NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT ck_email_templates_status CHECK (status IN ('draft','approved','retired')),
    FOREIGN KEY(organization_id) REFERENCES organizations (id) ON DELETE RESTRICT
);

CREATE INDEX ix_email_templates_resolution ON email_templates (organization_id, template_code, locale, status, version_number);

CREATE UNIQUE INDEX uq_email_templates_org_version ON email_templates (organization_id, template_code, locale, version_number) WHERE organization_id IS NOT NULL;

CREATE UNIQUE INDEX uq_email_templates_system_version ON email_templates (template_code, locale, version_number) WHERE organization_id IS NULL;

CREATE TABLE notification_preferences (
    id UUID NOT NULL,
    organization_id UUID NOT NULL,
    user_id UUID NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    in_app_enabled BOOLEAN NOT NULL,
    email_enabled BOOLEAN NOT NULL,
    digest_mode VARCHAR(20) NOT NULL,
    quiet_hours_start TIME WITHOUT TIME ZONE,
    quiet_hours_end TIME WITHOUT TIME ZONE,
    timezone VARCHAR(100) NOT NULL,
    version INTEGER NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT ck_notification_preferences_digest CHECK (digest_mode IN ('immediate','hourly','daily','none')),
    FOREIGN KEY(organization_id) REFERENCES organizations (id) ON DELETE RESTRICT,
    FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE RESTRICT,
    CONSTRAINT uq_notification_preferences_scope UNIQUE (organization_id, user_id, event_type)
);

CREATE INDEX ix_notification_preferences_user ON notification_preferences (organization_id, user_id);

CREATE TABLE outbox_events (
    id UUID NOT NULL,
    organization_id UUID NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    aggregate_type VARCHAR(100) NOT NULL,
    aggregate_id UUID NOT NULL,
    payload_hash VARCHAR(64) NOT NULL,
    status VARCHAR(20) NOT NULL,
    attempt_count INTEGER NOT NULL,
    available_at TIMESTAMP WITH TIME ZONE NOT NULL,
    processed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT ck_outbox_events_status CHECK (status IN ('pending','processing','processed','failed')),
    CONSTRAINT ck_outbox_events_attempts CHECK (attempt_count >= 0),
    FOREIGN KEY(organization_id) REFERENCES organizations (id) ON DELETE RESTRICT,
    CONSTRAINT uq_outbox_events_deduplication UNIQUE (organization_id, event_type, aggregate_type, aggregate_id, payload_hash)
);

CREATE INDEX ix_outbox_events_available ON outbox_events (status, available_at);

CREATE TABLE chat_rooms (
    id UUID NOT NULL,
    organization_id UUID NOT NULL,
    project_id UUID NOT NULL,
    room_type VARCHAR(30) NOT NULL,
    name VARCHAR(255) NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_by_user_id UUID NOT NULL,
    version INTEGER NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT ck_chat_rooms_type CHECK (room_type IN ('project','support','review','maintenance')),
    CONSTRAINT ck_chat_rooms_status CHECK (status IN ('active','archived','closed')),
    FOREIGN KEY(created_by_user_id) REFERENCES users (id) ON DELETE RESTRICT,
    FOREIGN KEY(organization_id) REFERENCES organizations (id) ON DELETE RESTRICT,
    FOREIGN KEY(project_id) REFERENCES projects (id) ON DELETE RESTRICT
);

CREATE INDEX ix_chat_rooms_project_status ON chat_rooms (project_id, status);

CREATE TABLE notifications (
    id UUID NOT NULL,
    organization_id UUID NOT NULL,
    user_id UUID NOT NULL,
    project_id UUID,
    event_type VARCHAR(100) NOT NULL,
    title VARCHAR(255) NOT NULL,
    body TEXT NOT NULL,
    severity VARCHAR(20) NOT NULL,
    status VARCHAR(20) NOT NULL,
    action_url VARCHAR(1024),
    deduplication_key VARCHAR(255) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    read_at TIMESTAMP WITH TIME ZONE,
    expires_at TIMESTAMP WITH TIME ZONE,
    version INTEGER NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT ck_notifications_internal_url CHECK (action_url IS NULL OR (action_url LIKE '/%%' AND action_url NOT LIKE '//%%')),
    CONSTRAINT ck_notifications_severity CHECK (severity IN ('info','success','warning','error','critical')),
    CONSTRAINT ck_notifications_status CHECK (status IN ('pending','delivered','read','dismissed','expired')),
    FOREIGN KEY(organization_id) REFERENCES organizations (id) ON DELETE RESTRICT,
    FOREIGN KEY(project_id) REFERENCES projects (id) ON DELETE RESTRICT,
    FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE RESTRICT,
    CONSTRAINT uq_notifications_deduplication UNIQUE (organization_id, user_id, deduplication_key)
);

CREATE INDEX ix_notifications_user_status_created ON notifications (organization_id, user_id, status, created_at);

CREATE TABLE chat_messages (
    id UUID NOT NULL,
    organization_id UUID NOT NULL,
    project_id UUID NOT NULL,
    chat_room_id UUID NOT NULL,
    sender_user_id UUID,
    message_type VARCHAR(30) NOT NULL,
    body TEXT NOT NULL,
    status VARCHAR(20) NOT NULL,
    reply_to_message_id UUID,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    edited_at TIMESTAMP WITH TIME ZONE,
    deleted_at TIMESTAMP WITH TIME ZONE,
    version INTEGER NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT ck_chat_messages_sender CHECK ((message_type IN ('system','ai') AND sender_user_id IS NULL) OR (message_type NOT IN ('system','ai') AND sender_user_id IS NOT NULL)),
    CONSTRAINT ck_chat_messages_type CHECK (message_type IN ('user','system','ai','review','change_request')),
    CONSTRAINT ck_chat_messages_status CHECK (status IN ('active','edited','deleted','moderated')),
    CONSTRAINT ck_chat_messages_body CHECK (length(trim(body)) BETWEEN 1 AND 10000),
    FOREIGN KEY(chat_room_id) REFERENCES chat_rooms (id) ON DELETE RESTRICT,
    FOREIGN KEY(organization_id) REFERENCES organizations (id) ON DELETE RESTRICT,
    FOREIGN KEY(project_id) REFERENCES projects (id) ON DELETE RESTRICT,
    FOREIGN KEY(reply_to_message_id) REFERENCES chat_messages (id) ON DELETE RESTRICT,
    FOREIGN KEY(sender_user_id) REFERENCES users (id) ON DELETE RESTRICT
);

CREATE INDEX ix_chat_messages_room_created ON chat_messages (chat_room_id, created_at);

CREATE TABLE email_messages (
    id UUID NOT NULL,
    organization_id UUID NOT NULL,
    project_id UUID,
    notification_id UUID,
    template_id UUID NOT NULL,
    recipient_user_id UUID NOT NULL,
    recipient_email_snapshot VARCHAR(320) NOT NULL,
    subject_snapshot VARCHAR(500) NOT NULL,
    body_text_snapshot TEXT NOT NULL,
    body_html_snapshot TEXT,
    status VARCHAR(20) NOT NULL,
    scheduled_at TIMESTAMP WITH TIME ZONE NOT NULL,
    sent_at TIMESTAMP WITH TIME ZONE,
    provider_message_id VARCHAR(255),
    attempt_count INTEGER NOT NULL,
    failure_code VARCHAR(100),
    failure_message_sanitized TEXT,
    deduplication_key VARCHAR(255) NOT NULL,
    version INTEGER NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT ck_email_messages_status CHECK (status IN ('draft','queued','sending','sent','delivered','failed','cancelled')),
    CONSTRAINT ck_email_messages_attempts CHECK (attempt_count >= 0),
    FOREIGN KEY(notification_id) REFERENCES notifications (id) ON DELETE RESTRICT,
    FOREIGN KEY(organization_id) REFERENCES organizations (id) ON DELETE RESTRICT,
    FOREIGN KEY(project_id) REFERENCES projects (id) ON DELETE RESTRICT,
    FOREIGN KEY(recipient_user_id) REFERENCES users (id) ON DELETE RESTRICT,
    FOREIGN KEY(template_id) REFERENCES email_templates (id) ON DELETE RESTRICT,
    CONSTRAINT uq_email_messages_deduplication UNIQUE (organization_id, deduplication_key)
);

CREATE INDEX ix_email_messages_schedule ON email_messages (status, scheduled_at);

CREATE TABLE notification_deliveries (
    id UUID NOT NULL,
    notification_id UUID NOT NULL,
    channel VARCHAR(20) NOT NULL,
    provider VARCHAR(30) NOT NULL,
    status VARCHAR(30) NOT NULL,
    attempt_count INTEGER NOT NULL,
    max_attempts INTEGER NOT NULL,
    scheduled_at TIMESTAMP WITH TIME ZONE NOT NULL,
    sent_at TIMESTAMP WITH TIME ZONE,
    delivered_at TIMESTAMP WITH TIME ZONE,
    failure_code VARCHAR(100),
    failure_message_sanitized TEXT,
    provider_message_id VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT ck_notification_deliveries_channel CHECK (channel IN ('in_app','email')),
    CONSTRAINT ck_notification_deliveries_status CHECK (status IN ('pending','scheduled','sending','sent','delivered','failed','cancelled')),
    CONSTRAINT ck_notification_deliveries_attempts CHECK (attempt_count >= 0 AND max_attempts BETWEEN 1 AND 10),
    FOREIGN KEY(notification_id) REFERENCES notifications (id) ON DELETE RESTRICT,
    CONSTRAINT uq_notification_deliveries_channel UNIQUE (notification_id, channel)
);

CREATE INDEX ix_notification_deliveries_schedule ON notification_deliveries (status, scheduled_at);

CREATE TABLE change_requests (
    id UUID NOT NULL,
    organization_id UUID NOT NULL,
    project_id UUID NOT NULL,
    chat_message_id UUID NOT NULL,
    requested_by_user_id UUID NOT NULL,
    title VARCHAR(255) NOT NULL,
    description TEXT NOT NULL,
    status VARCHAR(40) NOT NULL,
    priority VARCHAR(20) NOT NULL,
    scope_type VARCHAR(30) NOT NULL,
    estimate_id UUID,
    approved_by_user_id UUID,
    approved_at TIMESTAMP WITH TIME ZONE,
    version INTEGER NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT ck_change_requests_priority CHECK (priority IN ('low','normal','high','urgent')),
    CONSTRAINT ck_change_requests_scope CHECK (scope_type IN ('question','bug','minor_change','major_change','new_feature','infrastructure')),
    CONSTRAINT ck_change_requests_status CHECK (status IN ('draft','analyzing','awaiting_customer_approval','approved','rejected','in_progress','completed','cancelled')),
    FOREIGN KEY(approved_by_user_id) REFERENCES users (id) ON DELETE RESTRICT,
    FOREIGN KEY(chat_message_id) REFERENCES chat_messages (id) ON DELETE RESTRICT,
    FOREIGN KEY(estimate_id) REFERENCES estimates (id) ON DELETE RESTRICT,
    FOREIGN KEY(organization_id) REFERENCES organizations (id) ON DELETE RESTRICT,
    FOREIGN KEY(project_id) REFERENCES projects (id) ON DELETE RESTRICT,
    FOREIGN KEY(requested_by_user_id) REFERENCES users (id) ON DELETE RESTRICT
);

CREATE INDEX ix_change_requests_project_status ON change_requests (project_id, status);

CREATE TABLE chat_attachments (
    id UUID NOT NULL,
    organization_id UUID NOT NULL,
    project_id UUID NOT NULL,
    chat_message_id UUID NOT NULL,
    artifact_version_id UUID NOT NULL,
    filename VARCHAR(255) NOT NULL,
    mime_type VARCHAR(255) NOT NULL,
    file_size INTEGER NOT NULL,
    content_hash VARCHAR(64) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT ck_chat_attachments_size CHECK (file_size >= 0),
    FOREIGN KEY(artifact_version_id) REFERENCES artifact_versions (id) ON DELETE RESTRICT,
    FOREIGN KEY(chat_message_id) REFERENCES chat_messages (id) ON DELETE RESTRICT,
    FOREIGN KEY(organization_id) REFERENCES organizations (id) ON DELETE RESTRICT,
    FOREIGN KEY(project_id) REFERENCES projects (id) ON DELETE RESTRICT,
    CONSTRAINT uq_chat_attachments_version UNIQUE (chat_message_id, artifact_version_id)
);

CREATE TABLE document_generation_jobs (
    id UUID NOT NULL,
    organization_id UUID NOT NULL,
    project_id UUID NOT NULL,
    document_type VARCHAR(50) NOT NULL,
    template_id UUID,
    artifact_id UUID,
    artifact_version_id UUID,
    status VARCHAR(20) NOT NULL,
    output_format VARCHAR(20) NOT NULL,
    input_payload_hash VARCHAR(64) NOT NULL,
    storage_key VARCHAR(1024),
    content_hash VARCHAR(64),
    file_size INTEGER,
    attempt_count INTEGER NOT NULL,
    max_attempts INTEGER NOT NULL,
    failure_code VARCHAR(100),
    failure_message_sanitized TEXT,
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    version INTEGER NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT ck_document_jobs_output CHECK (output_format IN ('pdf','docx','xlsx','html','markdown')),
    CONSTRAINT ck_document_jobs_status CHECK (status IN ('queued','processing','completed','failed','cancelled')),
    CONSTRAINT ck_document_jobs_attempts CHECK (attempt_count >= 0 AND max_attempts BETWEEN 1 AND 10),
    FOREIGN KEY(artifact_id) REFERENCES artifacts (id) ON DELETE RESTRICT,
    FOREIGN KEY(artifact_version_id) REFERENCES artifact_versions (id) ON DELETE RESTRICT,
    FOREIGN KEY(organization_id) REFERENCES organizations (id) ON DELETE RESTRICT,
    FOREIGN KEY(project_id) REFERENCES projects (id) ON DELETE RESTRICT,
    FOREIGN KEY(template_id) REFERENCES document_templates (id) ON DELETE RESTRICT,
    CONSTRAINT uq_document_jobs_idempotency UNIQUE (organization_id, project_id, document_type, template_id, output_format, input_payload_hash)
);

CREATE INDEX ix_document_jobs_project_status ON document_generation_jobs (project_id, status);

CREATE TABLE change_request_impacts (
    id UUID NOT NULL,
    change_request_id UUID NOT NULL,
    impact_type VARCHAR(30) NOT NULL,
    target_reference VARCHAR(255),
    description TEXT NOT NULL,
    estimated_minutes INTEGER NOT NULL,
    estimated_amount NUMERIC(18, 8) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT ck_change_request_impacts_type CHECK (impact_type IN ('screen','api','database','document','test','infrastructure','schedule','cost')),
    CONSTRAINT ck_change_request_impacts_values CHECK (estimated_minutes >= 0 AND estimated_amount >= 0),
    FOREIGN KEY(change_request_id) REFERENCES change_requests (id) ON DELETE RESTRICT
);

CREATE INDEX ix_change_request_impacts_request ON change_request_impacts (change_request_id);

CREATE FUNCTION prevent_communication_hard_delete() RETURNS trigger AS $$
        BEGIN RAISE EXCEPTION 'communication records require logical deletion'; END;
        $$ LANGUAGE plpgsql;
        CREATE TRIGGER notifications_no_delete BEFORE DELETE ON notifications FOR EACH ROW EXECUTE FUNCTION prevent_communication_hard_delete();
        CREATE TRIGGER chat_messages_no_delete BEFORE DELETE ON chat_messages FOR EACH ROW EXECUTE FUNCTION prevent_communication_hard_delete();

        CREATE FUNCTION prevent_approved_template_mutation() RETURNS trigger AS $$
        BEGIN
            IF OLD.status = 'approved' THEN RAISE EXCEPTION 'approved templates are immutable'; END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        CREATE TRIGGER email_templates_approved_immutable BEFORE UPDATE ON email_templates FOR EACH ROW EXECUTE FUNCTION prevent_approved_template_mutation();
        CREATE TRIGGER document_templates_approved_immutable BEFORE UPDATE ON document_templates FOR EACH ROW EXECUTE FUNCTION prevent_approved_template_mutation();

        CREATE FUNCTION prevent_change_impact_mutation() RETURNS trigger AS $$
        BEGIN RAISE EXCEPTION 'change request impacts are append-only'; END;
        $$ LANGUAGE plpgsql;
        CREATE TRIGGER change_request_impacts_append_only BEFORE UPDATE OR DELETE ON change_request_impacts FOR EACH ROW EXECUTE FUNCTION prevent_change_impact_mutation();;

UPDATE alembic_version SET version_num='d8685773bc4a' WHERE alembic_version.version_num = '215db73ed802';

-- Running upgrade d8685773bc4a -> 6b1e4c9f2a10

ALTER TABLE outbox_events ADD COLUMN max_attempts INTEGER DEFAULT '5' NOT NULL;

ALTER TABLE outbox_events ADD COLUMN locked_at TIMESTAMP WITH TIME ZONE;

ALTER TABLE outbox_events ADD COLUMN locked_by VARCHAR(100);

ALTER TABLE outbox_events ADD COLUMN lease_expires_at TIMESTAMP WITH TIME ZONE;

ALTER TABLE outbox_events ADD COLUMN heartbeat_at TIMESTAMP WITH TIME ZONE;

ALTER TABLE outbox_events ADD COLUMN last_error_code VARCHAR(100);

ALTER TABLE outbox_events ADD COLUMN dead_lettered_at TIMESTAMP WITH TIME ZONE;

DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM outbox_events WHERE status NOT IN
          ('pending','processed','failed','queued','processing','completed','retry_wait','dead_letter'))
        THEN RAISE EXCEPTION 'outbox_events contains status outside replacement CHECK';
        END IF; END $$;

ALTER TABLE outbox_events DROP CONSTRAINT ck_outbox_events_status;

ALTER TABLE outbox_events ADD CONSTRAINT ck_outbox_events_status CHECK (status IN ('pending','processed','failed','queued','processing','completed','retry_wait','dead_letter'));

CREATE INDEX ix_outbox_events_lease ON outbox_events (status, available_at, lease_expires_at);

UPDATE alembic_version SET version_num='6b1e4c9f2a10' WHERE alembic_version.version_num = 'd8685773bc4a';

-- Running upgrade 6b1e4c9f2a10 -> 7c2f9a1e4d30

CREATE INDEX ix_audit_logs_org_cursor ON audit_logs (organization_id, created_at DESC, id DESC);

CREATE INDEX ix_notifications_org_cursor ON notifications (organization_id, created_at DESC, id DESC);

CREATE INDEX ix_chat_messages_room_cursor ON chat_messages (organization_id, chat_room_id, created_at DESC, id DESC);

CREATE INDEX ix_reviews_org_cursor ON reviews (organization_id, created_at DESC, id DESC);

CREATE INDEX ix_outbox_events_claim ON outbox_events (status, available_at, created_at, id);

UPDATE alembic_version SET version_num='7c2f9a1e4d30' WHERE alembic_version.version_num = '6b1e4c9f2a10';

-- Running upgrade 7c2f9a1e4d30 -> 8d4f2a7c9b11

ALTER TABLE workflow_jobs ADD COLUMN resume_block_reason VARCHAR(255);

ALTER TABLE workflow_jobs ADD COLUMN resume_blocked_at TIMESTAMP WITH TIME ZONE;

ALTER TABLE workflow_jobs ADD COLUMN parent_job_id UUID;

ALTER TABLE workflow_jobs ADD COLUMN idempotency_key VARCHAR(64);

ALTER TABLE workflow_jobs ADD CONSTRAINT fk_workflow_jobs_parent_job FOREIGN KEY(parent_job_id) REFERENCES workflow_jobs (id) ON DELETE RESTRICT;

ALTER TABLE workflow_jobs ADD CONSTRAINT uq_workflow_jobs_idempotency_key UNIQUE (idempotency_key);

ALTER TABLE document_generation_jobs ADD COLUMN resume_block_reason VARCHAR(255);

ALTER TABLE document_generation_jobs ADD COLUMN resume_blocked_at TIMESTAMP WITH TIME ZONE;

ALTER TABLE document_generation_jobs ADD COLUMN parent_job_id UUID;

ALTER TABLE document_generation_jobs ADD COLUMN idempotency_key VARCHAR(64);

ALTER TABLE document_generation_jobs ADD CONSTRAINT fk_document_generation_jobs_parent_job FOREIGN KEY(parent_job_id) REFERENCES document_generation_jobs (id) ON DELETE RESTRICT;

ALTER TABLE document_generation_jobs ADD CONSTRAINT uq_document_generation_jobs_idempotency_key UNIQUE (idempotency_key);

CREATE TABLE workflow_job_inputs (
    id UUID NOT NULL,
    organization_id UUID NOT NULL,
    project_id UUID NOT NULL,
    workflow_job_id UUID,
    document_job_id UUID,
    input_type VARCHAR(30) NOT NULL,
    schema_version VARCHAR(20) NOT NULL,
    source_reference_type VARCHAR(50) NOT NULL,
    source_reference_id UUID NOT NULL,
    actor_user_id UUID NOT NULL,
    access_context_hash VARCHAR(64) NOT NULL,
    settings_snapshot JSONB NOT NULL,
    template_snapshot JSONB NOT NULL,
    input_payload JSONB NOT NULL,
    input_payload_hash VARCHAR(64) NOT NULL,
    idempotency_key VARCHAR(64) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY(organization_id) REFERENCES organizations (id) ON DELETE RESTRICT,
    FOREIGN KEY(project_id) REFERENCES projects (id) ON DELETE RESTRICT,
    FOREIGN KEY(actor_user_id) REFERENCES users (id) ON DELETE RESTRICT,
    FOREIGN KEY(workflow_job_id) REFERENCES workflow_jobs (id) ON DELETE RESTRICT,
    FOREIGN KEY(document_job_id) REFERENCES document_generation_jobs (id) ON DELETE RESTRICT,
    UNIQUE (workflow_job_id),
    UNIQUE (document_job_id),
    UNIQUE (idempotency_key),
    CONSTRAINT ck_workflow_job_inputs_one_job CHECK ((workflow_job_id IS NOT NULL)::int + (document_job_id IS NOT NULL)::int = 1),
    CONSTRAINT ck_workflow_job_inputs_type CHECK (input_type IN ('document','ai_workflow'))
);

CREATE INDEX ix_workflow_job_inputs_tenant ON workflow_job_inputs (organization_id, project_id);

CREATE TABLE workflow_job_steps (
    id UUID NOT NULL,
    workflow_input_id UUID NOT NULL,
    step_name VARCHAR(50) NOT NULL,
    status VARCHAR(20) NOT NULL,
    idempotency_key VARCHAR(64) NOT NULL,
    result_reference VARCHAR(1024),
    result_hash VARCHAR(64),
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    attempt_count INTEGER NOT NULL,
    last_error_code VARCHAR(100),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY(workflow_input_id) REFERENCES workflow_job_inputs (id) ON DELETE RESTRICT,
    CONSTRAINT uq_workflow_job_steps_name UNIQUE (workflow_input_id, step_name),
    UNIQUE (idempotency_key),
    CONSTRAINT ck_workflow_job_steps_status CHECK (status IN ('pending','running','completed','failed')),
    CONSTRAINT ck_workflow_job_steps_attempts CHECK (attempt_count >= 0)
);

CREATE FUNCTION prevent_workflow_snapshot_mutation() RETURNS trigger AS $$ BEGIN RAISE EXCEPTION 'workflow snapshots and completed steps are immutable'; END; $$ LANGUAGE plpgsql;

CREATE TRIGGER workflow_job_inputs_immutable BEFORE UPDATE OR DELETE ON workflow_job_inputs FOR EACH ROW EXECUTE FUNCTION prevent_workflow_snapshot_mutation();

CREATE TRIGGER workflow_job_steps_completed_immutable BEFORE UPDATE OR DELETE ON workflow_job_steps FOR EACH ROW WHEN (OLD.status = 'completed') EXECUTE FUNCTION prevent_workflow_snapshot_mutation();

UPDATE alembic_version SET version_num='8d4f2a7c9b11' WHERE alembic_version.version_num = '7c2f9a1e4d30';

COMMIT;
