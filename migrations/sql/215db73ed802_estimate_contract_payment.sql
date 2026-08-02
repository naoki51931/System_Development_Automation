BEGIN;

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

COMMIT;
