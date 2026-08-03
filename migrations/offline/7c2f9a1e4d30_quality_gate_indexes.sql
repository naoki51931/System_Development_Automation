-- Offline review artifact only. Apply through Alembic after approval; local PostgreSQL only in this phase.
BEGIN;
CREATE INDEX ix_audit_logs_org_cursor ON audit_logs (organization_id, created_at DESC, id);
CREATE INDEX ix_notifications_org_cursor ON notifications (organization_id, created_at DESC, id);
CREATE INDEX ix_chat_messages_room_cursor ON chat_messages (room_id, created_at DESC, id);
CREATE INDEX ix_reviews_org_cursor ON reviews (organization_id, created_at DESC, id);
CREATE INDEX ix_outbox_events_claim ON outbox_events (status, available_at, lease_expires_at, created_at);
COMMIT;
