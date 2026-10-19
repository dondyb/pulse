"""Shared dispatch logic used by Send Now, the cron task, and manual retries.

Dispatching writes the recipient snapshot, a delivery run, one job per recipient,
and one outbox row per job inside the caller's transaction. Publishing to NATS
happens afterwards (see app.services.outbox).
"""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Campaign, CampaignRecipient, Contact, DeliveryJob, DeliveryRun
from app.services import activity
from app.timeutil import utcnow

AUDIENCE_LABELS = {
    "all_subscribers": "All Subscribers",
    "active_customers": "Active Customers",
    "trial_users": "Trial Users",
    "vip_customers": "VIP Customers",
}

# Which contact segments each audience includes. None means every segment.
AUDIENCE_SEGMENTS: dict[str, tuple[str, ...] | None] = {
    "all_subscribers": None,
    "active_customers": ("active_customer", "vip_customer"),
    "trial_users": ("trial_user",),
    "vip_customers": ("vip_customer",),
}


def audience_condition(audience: str):
    segments = AUDIENCE_SEGMENTS[audience]
    condition = Contact.subscribed.is_(True)
    if segments is not None:
        condition = condition & Contact.segment.in_(segments)
    return condition


def eligible_count(session: Session, audience: str) -> int:
    return session.scalar(select(func.count()).select_from(Contact).where(audience_condition(audience))) or 0


@dataclass
class DispatchResult:
    campaign_id: int
    recipient_count: int
    run_id: int | None


def _audience_sql(audience: str) -> tuple[str, dict]:
    segments = AUDIENCE_SEGMENTS[audience]
    if segments is None:
        return "subscribed", {}
    return "subscribed AND segment = ANY(:segments)", {"segments": list(segments)}


def create_run(session: Session, campaign: Campaign, kind: str, recipient_ids: list[int], now: datetime) -> DeliveryRun:
    """Create a delivery run with one job and one outbox record per recipient."""
    settings = get_settings()
    run_number = (
        session.scalar(select(func.coalesce(func.max(DeliveryRun.run_number), 0)).where(DeliveryRun.campaign_id == campaign.id))
        + 1
    )
    run = DeliveryRun(campaign_id=campaign.id, run_number=run_number, kind=kind, status="active", job_count=len(recipient_ids))
    session.add(run)
    session.flush()

    session.execute(
        text(
            """
            INSERT INTO delivery_jobs (run_id, campaign_id, recipient_id, status, max_attempts, next_attempt_at)
            SELECT :run_id, :campaign_id, r, 'queued', :max_attempts, :now FROM unnest(CAST(:ids AS bigint[])) AS r
            """
        ),
        {
            "run_id": run.id,
            "campaign_id": campaign.id,
            "max_attempts": settings.delivery_max_attempts,
            "now": now,
            "ids": recipient_ids,
        },
    )
    session.execute(
        text(
            """
            INSERT INTO outbox (job_id, message_id, subject, payload, status, available_at)
            SELECT j.id, 'job-' || j.id, :subject,
                   jsonb_build_object('job_id', j.id, 'campaign_id', j.campaign_id, 'run_id', j.run_id),
                   'pending', :now
            FROM delivery_jobs j WHERE j.run_id = :run_id
            """
        ),
        {"subject": settings.nats_subject, "run_id": run.id, "now": now},
    )
    return run


def dispatch_campaign(session: Session, campaign: Campaign, now: datetime | None = None) -> DispatchResult:
    """Snapshot recipients and enqueue delivery. The caller must hold a row lock on `campaign`."""
    now = now or utcnow()
    if campaign.status not in ("draft", "scheduled"):
        raise ValueError(f"campaign {campaign.id} cannot be dispatched from status {campaign.status}")

    where, params = _audience_sql(campaign.audience)
    recipient_ids = list(
        session.scalars(
            text(
                f"""
                INSERT INTO campaign_recipients (campaign_id, contact_id, name, email, status)
                SELECT :campaign_id, id, name, email, 'pending' FROM contacts WHERE {where}
                ORDER BY id
                ON CONFLICT (campaign_id, contact_id) DO NOTHING
                RETURNING id
                """
            ),
            {"campaign_id": campaign.id, **params},
        )
    )
    recipient_ids.sort()

    campaign.dispatched_at = now
    campaign.recipient_count = len(recipient_ids)
    label = AUDIENCE_LABELS[campaign.audience]

    if not recipient_ids:
        campaign.status = "completed"
        campaign.completed_at = now
        campaign.status_note = "No eligible recipients"
        activity.record(
            session,
            "campaign.completed",
            f"“{campaign.name}” completed — no eligible recipients in {label}",
            campaign_id=campaign.id,
            level="warning",
            at=now,
        )
        return DispatchResult(campaign.id, 0, None)

    run = create_run(session, campaign, "initial", recipient_ids, now)
    campaign.status = "processing"
    campaign.status_note = None
    activity.record(
        session,
        "campaign.dispatched",
        f"“{campaign.name}” started sending to {len(recipient_ids)} recipients in {label}",
        campaign_id=campaign.id,
        at=now,
    )
    return DispatchResult(campaign.id, len(recipient_ids), run.id)


def dispatch_next_due(session: Session, now: datetime | None = None) -> DispatchResult | None:
    """Claim one due scheduled campaign (skipping rows locked by others) and dispatch it."""
    now = now or utcnow()
    campaign = session.scalars(
        select(Campaign)
        .where(Campaign.status == "scheduled", Campaign.scheduled_at <= now)
        .order_by(Campaign.scheduled_at, Campaign.id)
        .limit(1)
        .with_for_update(skip_locked=True)
    ).first()
    if campaign is None:
        return None
    return dispatch_campaign(session, campaign, now)


def recipient_counts(session: Session, campaign_id: int) -> dict[str, int]:
    rows = session.execute(
        select(CampaignRecipient.status, func.count())
        .where(CampaignRecipient.campaign_id == campaign_id)
        .group_by(CampaignRecipient.status)
    ).all()
    counts = {"pending": 0, "delivered": 0, "failed": 0, "skipped": 0}
    counts.update({status: count for status, count in rows})
    counts["total"] = sum(counts[k] for k in ("pending", "delivered", "failed", "skipped"))
    return counts


def finish_run_if_done(session: Session, run_id: int, now: datetime | None = None) -> bool:
    """Close the run and complete the campaign once every job is terminal.

    Locks the run row so concurrent finalizers serialize; the last one sees all
    other jobs committed and completes the campaign exactly once.
    """
    now = now or utcnow()
    run = session.scalars(select(DeliveryRun).where(DeliveryRun.id == run_id).with_for_update()).one()
    if run.status != "active":
        return False
    remaining = session.scalar(
        select(func.count())
        .select_from(DeliveryJob)
        .where(DeliveryJob.run_id == run_id, DeliveryJob.status.not_in(("delivered", "failed", "skipped")))
    )
    if remaining:
        return False

    run.status = "finished"
    run.finished_at = now
    campaign = session.scalars(select(Campaign).where(Campaign.id == run.campaign_id).with_for_update()).one()
    if campaign.status != "processing":
        return True
    counts = recipient_counts(session, campaign.id)
    if counts["pending"]:
        return True

    campaign.status = "completed"
    campaign.completed_at = now
    parts = [f"{counts['delivered']} delivered"]
    if counts["failed"]:
        parts.append(f"{counts['failed']} failed")
    if counts["skipped"]:
        parts.append(f"{counts['skipped']} skipped")
    campaign.status_note = ", ".join(parts)
    activity.record(
        session,
        "campaign.completed",
        f"“{campaign.name}” finished sending: {campaign.status_note}",
        campaign_id=campaign.id,
        level="warning" if counts["failed"] else "success",
        at=now,
    )
    return True
