"""Database schema. Status columns are plain strings guarded by CHECK constraints."""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

SEGMENTS = ("active_customer", "trial_user", "vip_customer", "prospect")
AUDIENCES = ("all_subscribers", "active_customers", "trial_users", "vip_customers")
CAMPAIGN_STATUSES = ("draft", "scheduled", "processing", "completed", "cancelled")
RECIPIENT_STATUSES = ("pending", "delivered", "failed", "skipped")
JOB_STATUSES = ("queued", "processing", "retrying", "delivered", "failed", "skipped")
JOB_TERMINAL = ("delivered", "failed", "skipped")
RUN_KINDS = ("initial", "manual_retry")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class Base(DeclarativeBase):
    pass


TS = DateTime(timezone=True)


class Contact(Base):
    __tablename__ = "contacts"
    __table_args__ = (
        CheckConstraint(_in("segment", SEGMENTS), name="ck_contacts_segment"),
        Index("uq_contacts_email_lower", func.lower(text("email")), unique=True),
        Index("ix_contacts_segment_subscribed", "segment", "subscribed"),
        Index("ix_contacts_created_at", "created_at"),
        Index(
            "ix_contacts_search_trgm",
            text("(lower(name || ' ' || email || ' ' || company)) gin_trgm_ops"),
            postgresql_using="gin",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(254))
    company: Mapped[str] = mapped_column(String(160), default="")
    segment: Mapped[str] = mapped_column(String(32))
    subscribed: Mapped[bool] = mapped_column(Boolean, default=True)
    unsubscribed_at: Mapped[datetime | None] = mapped_column(TS)
    created_at: Mapped[datetime] = mapped_column(TS, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(TS, server_default=func.now(), onupdate=func.now())


class Campaign(Base):
    __tablename__ = "campaigns"
    __table_args__ = (
        CheckConstraint(_in("status", CAMPAIGN_STATUSES), name="ck_campaigns_status"),
        CheckConstraint(_in("audience", AUDIENCES), name="ck_campaigns_audience"),
        CheckConstraint("status <> 'scheduled' OR scheduled_at IS NOT NULL", name="ck_campaigns_scheduled_at"),
        Index("ix_campaigns_status", "status"),
        Index("ix_campaigns_due", "scheduled_at", postgresql_where=text("status = 'scheduled'")),
        Index("ix_campaigns_created_at", "created_at"),
        Index("ix_campaigns_name_trgm", text("lower(name) gin_trgm_ops"), postgresql_using="gin"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    subject: Mapped[str] = mapped_column(String(200), default="")
    body: Mapped[str] = mapped_column(Text, default="")
    audience: Mapped[str] = mapped_column(String(32))
    channel: Mapped[str] = mapped_column(String(16), default="email")
    status: Mapped[str] = mapped_column(String(16), default="draft")
    status_note: Mapped[str | None] = mapped_column(String(200))
    scheduled_at: Mapped[datetime | None] = mapped_column(TS)
    dispatched_at: Mapped[datetime | None] = mapped_column(TS)
    completed_at: Mapped[datetime | None] = mapped_column(TS)
    cancelled_at: Mapped[datetime | None] = mapped_column(TS)
    recipient_count: Mapped[int] = mapped_column(Integer, default=0)
    duplicated_from_id: Mapped[int | None] = mapped_column(ForeignKey("campaigns.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(TS, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(TS, server_default=func.now(), onupdate=func.now())


class DeliveryRun(Base):
    """One bounded pass over a set of recipients: the initial dispatch or a manual retry."""

    __tablename__ = "delivery_runs"
    __table_args__ = (
        UniqueConstraint("campaign_id", "run_number", name="uq_delivery_runs_campaign_number"),
        CheckConstraint(_in("kind", RUN_KINDS), name="ck_delivery_runs_kind"),
        CheckConstraint(_in("status", ("active", "finished")), name="ck_delivery_runs_status"),
        # At most one active run per campaign: blocks duplicate retry runs at the database level.
        Index("uq_delivery_runs_one_active", "campaign_id", unique=True, postgresql_where=text("status = 'active'")),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"))
    run_number: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16), default="active")
    job_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(TS, server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(TS)


class CampaignRecipient(Base):
    """Snapshot of who a campaign targets, and their overall outcome."""

    __tablename__ = "campaign_recipients"
    __table_args__ = (
        UniqueConstraint("campaign_id", "contact_id", name="uq_campaign_recipients_contact"),
        CheckConstraint(_in("status", RECIPIENT_STATUSES), name="ck_campaign_recipients_status"),
        Index("ix_campaign_recipients_campaign_status", "campaign_id", "status"),
        Index("ix_campaign_recipients_finished_at", "finished_at"),
        Index("ix_campaign_recipients_contact", "contact_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"))
    contact_id: Mapped[int] = mapped_column(ForeignKey("contacts.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(254))
    status: Mapped[str] = mapped_column(String(16), default="pending")
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(String(300))
    finished_at: Mapped[datetime | None] = mapped_column(TS)
    created_at: Mapped[datetime] = mapped_column(TS, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(TS, server_default=func.now(), onupdate=func.now())

    contact: Mapped[Contact] = relationship()


class DeliveryJob(Base):
    """A recipient's delivery within one run. Queue messages reference this row."""

    __tablename__ = "delivery_jobs"
    __table_args__ = (
        UniqueConstraint("run_id", "recipient_id", name="uq_delivery_jobs_run_recipient"),
        CheckConstraint(_in("status", JOB_STATUSES), name="ck_delivery_jobs_status"),
        Index("ix_delivery_jobs_status_next", "status", "next_attempt_at"),
        Index("ix_delivery_jobs_campaign", "campaign_id", "status"),
        Index("ix_delivery_jobs_run", "run_id", "status"),
        Index("ix_delivery_jobs_updated_at", "updated_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("delivery_runs.id", ondelete="CASCADE"))
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"))
    recipient_id: Mapped[int] = mapped_column(ForeignKey("campaign_recipients.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(16), default="queued")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    next_attempt_at: Mapped[datetime | None] = mapped_column(TS)
    locked_until: Mapped[datetime | None] = mapped_column(TS)
    locked_by: Mapped[str | None] = mapped_column(String(80))
    last_error: Mapped[str | None] = mapped_column(String(300))
    first_started_at: Mapped[datetime | None] = mapped_column(TS)
    last_started_at: Mapped[datetime | None] = mapped_column(TS)
    finished_at: Mapped[datetime | None] = mapped_column(TS)
    created_at: Mapped[datetime] = mapped_column(TS, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(TS, server_default=func.now(), onupdate=func.now())

    recipient: Mapped[CampaignRecipient] = relationship()


class DeliveryAttempt(Base):
    __tablename__ = "delivery_attempts"
    __table_args__ = (
        # One record per execution of a job attempt; redelivered messages reuse it.
        UniqueConstraint("job_id", "attempt_number", name="uq_delivery_attempts_job_attempt"),
        CheckConstraint(_in("outcome", ("in_progress", "success", "failure")), name="ck_delivery_attempts_outcome"),
        Index("ix_delivery_attempts_recipient", "recipient_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("delivery_jobs.id", ondelete="CASCADE"))
    recipient_id: Mapped[int] = mapped_column(ForeignKey("campaign_recipients.id", ondelete="CASCADE"))
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"))
    attempt_number: Mapped[int] = mapped_column(Integer)
    outcome: Mapped[str] = mapped_column(String(16), default="in_progress")
    error: Mapped[str | None] = mapped_column(String(300))
    started_at: Mapped[datetime] = mapped_column(TS, server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(TS)


class OutboxMessage(Base):
    """Transactional outbox: rows are written with the jobs, then published to NATS."""

    __tablename__ = "outbox"
    __table_args__ = (
        CheckConstraint(_in("status", ("pending", "published")), name="ck_outbox_status"),
        UniqueConstraint("message_id", name="uq_outbox_message_id"),
        Index("ix_outbox_pending", "available_at", "id", postgresql_where=text("status = 'pending'")),
        Index("ix_outbox_job", "job_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("delivery_jobs.id", ondelete="CASCADE"))
    message_id: Mapped[str] = mapped_column(String(80))
    subject: Mapped[str] = mapped_column(String(120))
    payload: Mapped[dict] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    available_at: Mapped[datetime] = mapped_column(TS, server_default=func.now())
    lease_until: Mapped[datetime | None] = mapped_column(TS)
    publish_attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(String(300))
    published_at: Mapped[datetime | None] = mapped_column(TS)
    created_at: Mapped[datetime] = mapped_column(TS, server_default=func.now())


class ActivityEvent(Base):
    __tablename__ = "activity_events"
    __table_args__ = (
        Index("ix_activity_events_created_at", "created_at"),
        Index("ix_activity_events_campaign", "campaign_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    campaign_id: Mapped[int | None] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"))
    recipient_id: Mapped[int | None] = mapped_column(ForeignKey("campaign_recipients.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(48))
    level: Mapped[str] = mapped_column(String(16), default="info")
    message: Mapped[str] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(TS, server_default=func.now())


class WorkerHeartbeat(Base):
    __tablename__ = "worker_heartbeats"

    worker_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    hostname: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(16), default="running")
    concurrency: Mapped[int] = mapped_column(Integer, default=1)
    jobs_processed: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime] = mapped_column(TS, server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(TS, server_default=func.now())


class CronRun(Base):
    __tablename__ = "cron_runs"
    __table_args__ = (
        CheckConstraint(_in("status", ("running", "success", "failed")), name="ck_cron_runs_status"),
        Index("ix_cron_runs_started_at", "started_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    task: Mapped[str] = mapped_column(String(48), default="dispatch_due")
    status: Mapped[str] = mapped_column(String(16), default="running")
    started_at: Mapped[datetime] = mapped_column(TS)
    finished_at: Mapped[datetime | None] = mapped_column(TS)
    campaigns_dispatched: Mapped[int] = mapped_column(Integer, default=0)
    outbox_published: Mapped[int] = mapped_column(Integer, default=0)
    outbox_pending: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(String(500))


class AppMeta(Base):
    __tablename__ = "app_meta"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(String(200))
    updated_at: Mapped[datetime] = mapped_column(TS, server_default=func.now())
