"""Initial schema.

Revision ID: 0001_initial
Revises:
Create Date: 2026-10-19
"""

from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


UPGRADE_SQL = """
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE contacts (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(120) NOT NULL,
    email VARCHAR(254) NOT NULL,
    company VARCHAR(160) NOT NULL DEFAULT '',
    segment VARCHAR(32) NOT NULL,
    subscribed BOOLEAN NOT NULL DEFAULT TRUE,
    unsubscribed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_contacts_segment CHECK (segment IN ('active_customer', 'trial_user', 'vip_customer', 'prospect'))
);
CREATE UNIQUE INDEX uq_contacts_email_lower ON contacts (lower(email));
CREATE INDEX ix_contacts_segment_subscribed ON contacts (segment, subscribed);
CREATE INDEX ix_contacts_created_at ON contacts (created_at);
CREATE INDEX ix_contacts_search_trgm ON contacts
    USING gin ((lower(name || ' ' || email || ' ' || company)) gin_trgm_ops);

CREATE TABLE campaigns (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(160) NOT NULL,
    subject VARCHAR(200) NOT NULL DEFAULT '',
    body TEXT NOT NULL DEFAULT '',
    audience VARCHAR(32) NOT NULL,
    channel VARCHAR(16) NOT NULL DEFAULT 'email',
    status VARCHAR(16) NOT NULL DEFAULT 'draft',
    status_note VARCHAR(200),
    scheduled_at TIMESTAMPTZ,
    dispatched_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    cancelled_at TIMESTAMPTZ,
    recipient_count INTEGER NOT NULL DEFAULT 0,
    duplicated_from_id BIGINT REFERENCES campaigns (id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_campaigns_status CHECK (status IN ('draft', 'scheduled', 'processing', 'completed', 'cancelled')),
    CONSTRAINT ck_campaigns_audience CHECK (audience IN ('all_subscribers', 'active_customers', 'trial_users', 'vip_customers')),
    CONSTRAINT ck_campaigns_scheduled_at CHECK (status <> 'scheduled' OR scheduled_at IS NOT NULL)
);
CREATE INDEX ix_campaigns_status ON campaigns (status);
CREATE INDEX ix_campaigns_due ON campaigns (scheduled_at) WHERE status = 'scheduled';
CREATE INDEX ix_campaigns_created_at ON campaigns (created_at);
CREATE INDEX ix_campaigns_name_trgm ON campaigns USING gin ((lower(name)) gin_trgm_ops);

CREATE TABLE delivery_runs (
    id BIGSERIAL PRIMARY KEY,
    campaign_id BIGINT NOT NULL REFERENCES campaigns (id) ON DELETE CASCADE,
    run_number INTEGER NOT NULL,
    kind VARCHAR(16) NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'active',
    job_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ,
    CONSTRAINT uq_delivery_runs_campaign_number UNIQUE (campaign_id, run_number),
    CONSTRAINT ck_delivery_runs_kind CHECK (kind IN ('initial', 'manual_retry')),
    CONSTRAINT ck_delivery_runs_status CHECK (status IN ('active', 'finished'))
);
CREATE UNIQUE INDEX uq_delivery_runs_one_active ON delivery_runs (campaign_id) WHERE status = 'active';

CREATE TABLE campaign_recipients (
    id BIGSERIAL PRIMARY KEY,
    campaign_id BIGINT NOT NULL REFERENCES campaigns (id) ON DELETE CASCADE,
    contact_id BIGINT NOT NULL REFERENCES contacts (id) ON DELETE CASCADE,
    name VARCHAR(120) NOT NULL,
    email VARCHAR(254) NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'pending',
    attempt_count INTEGER NOT NULL DEFAULT 0,
    last_error VARCHAR(300),
    finished_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_campaign_recipients_contact UNIQUE (campaign_id, contact_id),
    CONSTRAINT ck_campaign_recipients_status CHECK (status IN ('pending', 'delivered', 'failed', 'skipped'))
);
CREATE INDEX ix_campaign_recipients_campaign_status ON campaign_recipients (campaign_id, status);
CREATE INDEX ix_campaign_recipients_finished_at ON campaign_recipients (finished_at);
CREATE INDEX ix_campaign_recipients_contact ON campaign_recipients (contact_id);

CREATE TABLE delivery_jobs (
    id BIGSERIAL PRIMARY KEY,
    run_id BIGINT NOT NULL REFERENCES delivery_runs (id) ON DELETE CASCADE,
    campaign_id BIGINT NOT NULL REFERENCES campaigns (id) ON DELETE CASCADE,
    recipient_id BIGINT NOT NULL REFERENCES campaign_recipients (id) ON DELETE CASCADE,
    status VARCHAR(16) NOT NULL DEFAULT 'queued',
    attempts INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 3,
    next_attempt_at TIMESTAMPTZ,
    locked_until TIMESTAMPTZ,
    locked_by VARCHAR(80),
    last_error VARCHAR(300),
    first_started_at TIMESTAMPTZ,
    last_started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_delivery_jobs_run_recipient UNIQUE (run_id, recipient_id),
    CONSTRAINT ck_delivery_jobs_status CHECK (status IN ('queued', 'processing', 'retrying', 'delivered', 'failed', 'skipped'))
);
CREATE INDEX ix_delivery_jobs_status_next ON delivery_jobs (status, next_attempt_at);
CREATE INDEX ix_delivery_jobs_campaign ON delivery_jobs (campaign_id, status);
CREATE INDEX ix_delivery_jobs_run ON delivery_jobs (run_id, status);
CREATE INDEX ix_delivery_jobs_updated_at ON delivery_jobs (updated_at);

CREATE TABLE delivery_attempts (
    id BIGSERIAL PRIMARY KEY,
    job_id BIGINT NOT NULL REFERENCES delivery_jobs (id) ON DELETE CASCADE,
    recipient_id BIGINT NOT NULL REFERENCES campaign_recipients (id) ON DELETE CASCADE,
    campaign_id BIGINT NOT NULL REFERENCES campaigns (id) ON DELETE CASCADE,
    attempt_number INTEGER NOT NULL,
    outcome VARCHAR(16) NOT NULL DEFAULT 'in_progress',
    error VARCHAR(300),
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ,
    CONSTRAINT uq_delivery_attempts_job_attempt UNIQUE (job_id, attempt_number),
    CONSTRAINT ck_delivery_attempts_outcome CHECK (outcome IN ('in_progress', 'success', 'failure'))
);
CREATE INDEX ix_delivery_attempts_recipient ON delivery_attempts (recipient_id);

CREATE TABLE outbox (
    id BIGSERIAL PRIMARY KEY,
    job_id BIGINT NOT NULL REFERENCES delivery_jobs (id) ON DELETE CASCADE,
    message_id VARCHAR(80) NOT NULL,
    subject VARCHAR(120) NOT NULL,
    payload JSONB NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'pending',
    available_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    lease_until TIMESTAMPTZ,
    publish_attempts INTEGER NOT NULL DEFAULT 0,
    last_error VARCHAR(300),
    published_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_outbox_message_id UNIQUE (message_id),
    CONSTRAINT ck_outbox_status CHECK (status IN ('pending', 'published'))
);
CREATE INDEX ix_outbox_pending ON outbox (available_at, id) WHERE status = 'pending';
CREATE INDEX ix_outbox_job ON outbox (job_id);

CREATE TABLE activity_events (
    id BIGSERIAL PRIMARY KEY,
    campaign_id BIGINT REFERENCES campaigns (id) ON DELETE CASCADE,
    recipient_id BIGINT REFERENCES campaign_recipients (id) ON DELETE CASCADE,
    kind VARCHAR(48) NOT NULL,
    level VARCHAR(16) NOT NULL DEFAULT 'info',
    message VARCHAR(300) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_activity_events_created_at ON activity_events (created_at);
CREATE INDEX ix_activity_events_campaign ON activity_events (campaign_id, created_at);

CREATE TABLE worker_heartbeats (
    worker_id VARCHAR(80) PRIMARY KEY,
    hostname VARCHAR(120) NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'running',
    concurrency INTEGER NOT NULL DEFAULT 1,
    jobs_processed INTEGER NOT NULL DEFAULT 0,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE cron_runs (
    id BIGSERIAL PRIMARY KEY,
    task VARCHAR(48) NOT NULL DEFAULT 'dispatch_due',
    status VARCHAR(16) NOT NULL DEFAULT 'running',
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ,
    campaigns_dispatched INTEGER NOT NULL DEFAULT 0,
    outbox_published INTEGER NOT NULL DEFAULT 0,
    outbox_pending INTEGER NOT NULL DEFAULT 0,
    error VARCHAR(500),
    CONSTRAINT ck_cron_runs_status CHECK (status IN ('running', 'success', 'failed'))
);
CREATE INDEX ix_cron_runs_started_at ON cron_runs (started_at);

CREATE TABLE app_meta (
    key VARCHAR(64) PRIMARY KEY,
    value VARCHAR(200) NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""

DOWNGRADE_SQL = """
DROP TABLE IF EXISTS app_meta, cron_runs, worker_heartbeats, activity_events, outbox,
    delivery_attempts, delivery_jobs, campaign_recipients, delivery_runs, campaigns, contacts CASCADE;
"""


def upgrade() -> None:
    op.execute(UPGRADE_SQL)


def downgrade() -> None:
    op.execute(DOWNGRADE_SQL)
