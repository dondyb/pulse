"""Delivery job processing, independent of the queue transport.

A worker calls `begin_attempt` to claim a job, simulates the send outside any
transaction, then calls `complete_attempt` to persist the outcome. Each returns a
`Decision` telling the transport whether to acknowledge the message or ask for
redelivery after a delay. Callers must commit before acting on the decision.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import JOB_TERMINAL, Campaign, CampaignRecipient, Contact, DeliveryAttempt, DeliveryJob
from app.services import activity
from app.services.dispatch import finish_run_if_done
from app.services.simulation import SimulatedResult
from app.timeutil import utcnow


@dataclass(frozen=True)
class Decision:
    action: str  # "ack" or "nak"
    reason: str
    delay: float = 0.0


@dataclass(frozen=True)
class Claim:
    job_id: int
    campaign_id: int
    contact_id: int
    email: str
    attempt_number: int  # within this job's run
    overall_attempt: int  # across every run for this recipient


def _seconds_until(moment: datetime, now: datetime) -> float:
    return max((moment - now).total_seconds(), 0.5)


def begin_attempt(session: Session, job_id: int, worker_id: str, now: datetime | None = None) -> Claim | Decision:
    now = now or utcnow()
    settings = get_settings()
    job = session.scalars(select(DeliveryJob).where(DeliveryJob.id == job_id).with_for_update(skip_locked=True)).first()
    if job is None:
        if session.get(DeliveryJob, job_id) is None:
            return Decision("ack", "unknown job")
        return Decision("nak", "job locked by another worker", delay=2)

    if job.status in JOB_TERMINAL:
        return Decision("ack", f"duplicate message: job already {job.status}")
    if job.status == "processing" and job.locked_until and job.locked_until > now:
        return Decision("nak", "job leased by another worker", delay=_seconds_until(job.locked_until, now))
    if job.status == "retrying" and job.next_attempt_at and job.next_attempt_at > now:
        return Decision("nak", "retry not due yet", delay=_seconds_until(job.next_attempt_at, now))

    recipient = session.scalars(
        select(CampaignRecipient).where(CampaignRecipient.id == job.recipient_id).with_for_update()
    ).one()
    contact = session.get(Contact, recipient.contact_id)

    # Recheck consent immediately before delivering.
    if contact is None or not contact.subscribed:
        reason = "Contact unsubscribed before delivery"
        job.status = "skipped"
        job.finished_at = now
        job.locked_until = None
        job.last_error = reason
        recipient.status = "skipped"
        recipient.finished_at = now
        recipient.last_error = reason
        activity.record(
            session,
            "delivery.skipped",
            f"Skipped {recipient.email}: unsubscribed before delivery",
            campaign_id=job.campaign_id,
            recipient_id=recipient.id,
            level="warning",
            at=now,
        )
        session.flush()
        finish_run_if_done(session, job.run_id, now)
        return Decision("ack", "recipient skipped")

    if job.status == "processing":
        # Previous holder's lease expired mid-attempt: resume the same attempt record.
        attempt_number = job.attempts
    else:
        job.attempts += 1
        attempt_number = job.attempts
        recipient.attempt_count += 1
        session.execute(
            insert(DeliveryAttempt)
            .values(
                job_id=job.id,
                recipient_id=recipient.id,
                campaign_id=job.campaign_id,
                attempt_number=attempt_number,
                outcome="in_progress",
                started_at=now,
            )
            .on_conflict_do_nothing(constraint="uq_delivery_attempts_job_attempt")
        )

    job.status = "processing"
    job.locked_by = worker_id
    job.locked_until = now + timedelta(seconds=settings.job_lease_seconds)
    job.last_started_at = now
    job.first_started_at = job.first_started_at or now
    return Claim(job.id, job.campaign_id, recipient.contact_id, recipient.email, attempt_number, recipient.attempt_count)


def complete_attempt(
    session: Session, claim: Claim, result: SimulatedResult, worker_id: str, now: datetime | None = None
) -> Decision:
    now = now or utcnow()
    settings = get_settings()
    job = session.scalars(select(DeliveryJob).where(DeliveryJob.id == claim.job_id).with_for_update()).one()
    if job.status != "processing" or job.attempts != claim.attempt_number or job.locked_by != worker_id:
        # Another worker took over after our lease expired; its outcome wins.
        return Decision("ack", "stale attempt result discarded")

    recipient = session.scalars(
        select(CampaignRecipient).where(CampaignRecipient.id == job.recipient_id).with_for_update()
    ).one()
    attempt = session.scalars(
        select(DeliveryAttempt).where(
            DeliveryAttempt.job_id == job.id, DeliveryAttempt.attempt_number == claim.attempt_number
        )
    ).one()
    attempt.outcome = "success" if result.success else "failure"
    attempt.error = result.error
    attempt.finished_at = now
    job.locked_until = None
    job.locked_by = None

    campaign_name = session.scalar(select(Campaign.name).where(Campaign.id == job.campaign_id))
    decision = Decision("ack", "delivered")

    if result.success:
        job.status = "delivered"
        job.finished_at = now
        job.next_attempt_at = None
        recipient.status = "delivered"
        recipient.finished_at = now
        recipient.last_error = None
        activity.record(
            session,
            "delivery.delivered",
            f"Delivered “{campaign_name}” to {recipient.email}",
            campaign_id=job.campaign_id,
            recipient_id=recipient.id,
            level="success",
            at=now,
        )
    elif job.attempts < job.max_attempts:
        delay = settings.retry_delay_for(job.attempts)
        job.status = "retrying"
        job.next_attempt_at = now + timedelta(seconds=delay)
        job.last_error = result.error
        recipient.last_error = result.error
        activity.record(
            session,
            "delivery.retry_scheduled",
            f"Delivery to {recipient.email} failed (attempt {job.attempts} of {job.max_attempts}); retrying in {delay}s",
            campaign_id=job.campaign_id,
            recipient_id=recipient.id,
            level="warning",
            at=now,
        )
        decision = Decision("nak", "retry scheduled", delay=float(delay))
    else:
        job.status = "failed"
        job.finished_at = now
        job.next_attempt_at = None
        job.last_error = result.error
        recipient.status = "failed"
        recipient.finished_at = now
        recipient.last_error = result.error
        activity.record(
            session,
            "delivery.failed",
            f"Could not deliver to {recipient.email} after {job.attempts} attempts: {result.error}",
            campaign_id=job.campaign_id,
            recipient_id=recipient.id,
            level="error",
            at=now,
        )
        decision = Decision("ack", "failed permanently")

    session.flush()
    if job.status in JOB_TERMINAL:
        finish_run_if_done(session, job.run_id, now)
    return decision
