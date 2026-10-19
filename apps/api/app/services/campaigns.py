"""Campaign lifecycle: drafts, scheduling, Send Now, duplication, cancel, manual retry."""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import AUDIENCES, Campaign, CampaignRecipient, DeliveryRun
from app.services import activity
from app.services.dispatch import AUDIENCE_LABELS, create_run, dispatch_campaign, eligible_count
from app.services.errors import Conflict, NotFound, ValidationFailed
from app.timeutil import floor_minute, utcnow

ACTIONS = ("draft", "send", "schedule")


@dataclass
class CampaignInput:
    name: str
    subject: str
    body: str
    audience: str
    action: str
    scheduled_at: datetime | None = None


def _validate(session: Session, data: CampaignInput, now: datetime) -> datetime | None:
    errors: dict[str, str] = {}
    name = data.name.strip()
    if not name:
        errors["name"] = "Campaign name is required."
    elif len(name) > 160:
        errors["name"] = "Campaign name must be 160 characters or fewer."
    if data.audience not in AUDIENCES:
        errors["audience"] = "Choose an audience."
    if data.action not in ACTIONS:
        errors["action"] = "Unknown action."

    scheduled_at = None
    if data.action in ("send", "schedule"):
        if not data.subject.strip():
            errors["subject"] = "Email subject is required."
        if not data.body.strip():
            errors["body"] = "Message body is required."
        if "audience" not in errors and eligible_count(session, data.audience) == 0:
            errors["audience"] = "This audience has no subscribed contacts."
    if len(data.subject) > 200:
        errors["subject"] = "Email subject must be 200 characters or fewer."
    if len(data.body) > 20000:
        errors["body"] = "Message body must be 20,000 characters or fewer."

    if data.action == "schedule":
        if data.scheduled_at is None:
            errors["scheduled_at"] = "Choose a date and time."
        else:
            if data.scheduled_at.tzinfo is None:
                errors["scheduled_at"] = "Scheduled time must include a timezone."
            else:
                scheduled_at = floor_minute(data.scheduled_at)
                if scheduled_at <= now:
                    errors["scheduled_at"] = "Scheduled time must be in the future."
    if errors:
        raise ValidationFailed("Please fix the highlighted fields.", errors)
    return scheduled_at


def _apply(session: Session, campaign: Campaign, data: CampaignInput, now: datetime) -> Campaign:
    scheduled_at = _validate(session, data, now)
    campaign.name = data.name.strip()
    campaign.subject = data.subject.strip()
    campaign.body = data.body
    campaign.audience = data.audience
    label = AUDIENCE_LABELS[data.audience]

    if data.action == "draft":
        campaign.status = "draft"
        campaign.scheduled_at = None
        session.flush()
        return campaign
    if data.action == "schedule":
        campaign.status = "scheduled"
        campaign.scheduled_at = scheduled_at
        session.flush()
        activity.record(
            session,
            "campaign.scheduled",
            f"“{campaign.name}” scheduled for {label}",
            campaign_id=campaign.id,
            at=now,
        )
        return campaign
    # send now
    session.flush()
    dispatch_campaign(session, campaign, now)
    return campaign


def create_campaign(session: Session, data: CampaignInput) -> Campaign:
    now = utcnow()
    # Validation failures roll back the whole transaction, including this insert.
    campaign = Campaign(name=data.name.strip()[:160], audience="all_subscribers", status="draft")
    session.add(campaign)
    session.flush()
    activity.record(session, "campaign.created", f"“{campaign.name}” created", campaign_id=campaign.id, at=now)
    return _apply(session, campaign, data, now)


def lock_campaign(session: Session, campaign_id: int) -> Campaign:
    campaign = session.scalars(select(Campaign).where(Campaign.id == campaign_id).with_for_update()).first()
    if campaign is None:
        raise NotFound("Campaign not found.")
    return campaign


def update_campaign(session: Session, campaign_id: int, data: CampaignInput) -> Campaign:
    campaign = lock_campaign(session, campaign_id)
    if campaign.status != "draft":
        raise Conflict("Only draft campaigns can be edited.")
    return _apply(session, campaign, data, utcnow())


def duplicate_campaign(session: Session, campaign_id: int) -> Campaign:
    source = session.get(Campaign, campaign_id)
    if source is None:
        raise NotFound("Campaign not found.")
    copy = Campaign(
        name=f"{source.name} (copy)"[:160],
        subject=source.subject,
        body=source.body,
        audience=source.audience,
        status="draft",
        duplicated_from_id=source.id,
    )
    session.add(copy)
    session.flush()
    activity.record(session, "campaign.created", f"“{copy.name}” created from “{source.name}”", campaign_id=copy.id)
    return copy


def cancel_campaign(session: Session, campaign_id: int) -> Campaign:
    # Blocks while a dispatcher holds the row; afterwards the status check sees its result.
    campaign = lock_campaign(session, campaign_id)
    if campaign.status != "scheduled":
        if campaign.status == "processing":
            raise Conflict("This campaign has already started sending and can no longer be cancelled.")
        raise Conflict("Only scheduled campaigns can be cancelled.")
    now = utcnow()
    campaign.status = "cancelled"
    campaign.cancelled_at = now
    campaign.status_note = "Cancelled before sending"
    activity.record(session, "campaign.cancelled", f"“{campaign.name}” was cancelled", campaign_id=campaign.id, level="warning", at=now)
    return campaign


def retry_failed(session: Session, campaign_id: int) -> DeliveryRun:
    """Start a new bounded run for recipients whose deliveries failed. Prior attempts are kept."""
    campaign = lock_campaign(session, campaign_id)
    active = session.scalar(
        select(func.count()).select_from(DeliveryRun).where(DeliveryRun.campaign_id == campaign.id, DeliveryRun.status == "active")
    )
    if active:
        raise Conflict("A delivery run is already in progress for this campaign.")
    if campaign.status != "completed":
        raise Conflict("Failed deliveries can be retried once the campaign has finished sending.")
    failed = list(
        session.scalars(
            select(CampaignRecipient)
            .where(CampaignRecipient.campaign_id == campaign.id, CampaignRecipient.status == "failed")
            .order_by(CampaignRecipient.id)
        )
    )
    if not failed:
        raise Conflict("There are no failed deliveries to retry.")

    now = utcnow()
    for recipient in failed:
        recipient.status = "pending"
        recipient.finished_at = None
    try:
        with session.begin_nested():
            run = create_run(session, campaign, "manual_retry", [r.id for r in failed], now)
    except IntegrityError as exc:
        raise Conflict("A retry is already in progress.") from exc
    campaign.status = "processing"
    campaign.completed_at = None
    campaign.status_note = None
    activity.record(
        session,
        "campaign.retry_started",
        f"Retrying {len(failed)} failed deliveries for “{campaign.name}”",
        campaign_id=campaign.id,
        at=now,
    )
    return run
