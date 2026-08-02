BEGIN;

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

COMMIT;
