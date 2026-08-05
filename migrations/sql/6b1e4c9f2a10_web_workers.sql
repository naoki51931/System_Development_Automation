-- Offline additive migration; do not run against RDS in this phase.
ALTER TABLE outbox_events ADD COLUMN max_attempts INTEGER DEFAULT 5 NOT NULL;
ALTER TABLE outbox_events ADD COLUMN locked_at TIMESTAMPTZ;
ALTER TABLE outbox_events ADD COLUMN locked_by VARCHAR(100);
ALTER TABLE outbox_events ADD COLUMN lease_expires_at TIMESTAMPTZ;
ALTER TABLE outbox_events ADD COLUMN heartbeat_at TIMESTAMPTZ;
ALTER TABLE outbox_events ADD COLUMN last_error_code VARCHAR(100);
ALTER TABLE outbox_events ADD COLUMN dead_lettered_at TIMESTAMPTZ;
-- Preflight before replacing the CHECK. DROP/ADD takes ACCESS EXCLUSIVE locks;
-- schedule a maintenance window for a large table. This migration is not drop-free.
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM outbox_events WHERE status NOT IN ('pending','processed','failed','queued','processing','completed','retry_wait','dead_letter'))
  THEN RAISE EXCEPTION 'outbox_events contains status outside replacement CHECK';
  END IF;
END $$;
ALTER TABLE outbox_events DROP CONSTRAINT ck_outbox_events_status;
ALTER TABLE outbox_events ADD CONSTRAINT ck_outbox_events_status CHECK (status IN ('pending','processed','failed','queued','processing','completed','retry_wait','dead_letter'));
CREATE INDEX ix_outbox_events_lease ON outbox_events (status, available_at, lease_expires_at);
