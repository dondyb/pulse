"""Idempotent demo seed. Runs once per database; guarded by an app_meta marker
and a transaction-scoped advisory lock so concurrent init runs cannot double-seed."""

import logging
import random
import re
from datetime import datetime, timedelta

from sqlalchemy import insert, select, text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import (
    ActivityEvent,
    AppMeta,
    Campaign,
    CampaignRecipient,
    Contact,
    DeliveryAttempt,
    DeliveryJob,
    DeliveryRun,
)
from app.seed import data
from app.services.dispatch import AUDIENCE_LABELS, AUDIENCE_SEGMENTS
from app.services.simulation import is_bad_address, simulate
from app.timeutil import floor_minute, utcnow

log = logging.getLogger("pulse.seed")

SEED_KEY = "seed.version"
SEED_VERSION = "1"
ADVISORY_LOCK_ID = 74_210_001


def is_seeded(session: Session) -> bool:
    return session.get(AppMeta, SEED_KEY) is not None


def _slug(value: str) -> str:
    return re.sub(r"[^a-z]", "", value.lower())


def _contacts(rng: random.Random, now: datetime) -> list[dict]:
    segments = ["active_customer"] * 45 + ["trial_user"] * 22 + ["vip_customer"] * 12 + ["prospect"] * 21
    rows, seen = [], set()
    while len(rows) < 250:
        first, last = rng.choice(data.FIRST_NAMES), rng.choice(data.LAST_NAMES)
        company, domain = rng.choice(data.COMPANIES)
        local = f"{_slug(first)}.{_slug(last)}"
        email = f"{local}@{domain}"
        suffix = 2
        while email in seen:
            email = f"{local}{suffix}@{domain}"
            suffix += 1
        seen.add(email)
        created = now - timedelta(days=rng.uniform(32, 160), minutes=rng.randint(0, 1440))
        subscribed = rng.random() > 0.08
        segment = rng.choice(segments)
        if is_bad_address(email):
            # Keep hard-bouncing addresses out of the VIP and trial segments so some
            # historical campaigns finish fully delivered.
            segment = rng.choice(["active_customer", "prospect"])
        rows.append(
            {
                "name": f"{first} {last}",
                "email": email,
                "company": company,
                "segment": segment,
                "subscribed": subscribed,
                "unsubscribed_at": None if subscribed else now - timedelta(days=rng.uniform(0.5, 30)),
                "created_at": created,
                "updated_at": created,
            }
        )
    return rows


def _eligible_at(contacts: list[Contact], audience: str, moment: datetime) -> list[Contact]:
    segments = AUDIENCE_SEGMENTS[audience]
    result = []
    for c in contacts:
        if segments is not None and c.segment not in segments:
            continue
        if c.created_at > moment:
            continue
        if not c.subscribed and (c.unsubscribed_at is None or c.unsubscribed_at <= moment):
            continue
        result.append(c)
    return result


def _seed_history(session: Session, contacts: list[Contact], now: datetime) -> None:
    settings = get_settings()
    max_attempts = settings.delivery_max_attempts
    for index, (name, subject, body, audience, days_ago) in enumerate(data.HISTORY):
        dispatched = now - timedelta(days=days_ago)
        created = dispatched - timedelta(days=1, hours=index % 5)
        campaign = Campaign(
            name=name,
            subject=subject,
            body=body + data.SIGNATURE,
            audience=audience,
            status="processing",
            dispatched_at=dispatched,
            created_at=created,
            updated_at=dispatched,
        )
        if index % 3 == 0:
            campaign.scheduled_at = floor_minute(dispatched)
        session.add(campaign)
        session.flush()

        events: list[dict] = [
            dict(campaign_id=campaign.id, kind="campaign.created", level="info", message=f"“{name}” created", created_at=created)
        ]
        if campaign.scheduled_at:
            events.append(
                dict(
                    campaign_id=campaign.id,
                    kind="campaign.scheduled",
                    level="info",
                    message=f"“{name}” scheduled for {AUDIENCE_LABELS[audience]}",
                    created_at=created + timedelta(minutes=5),
                )
            )
        audience_contacts = _eligible_at(contacts, audience, dispatched)
        events.append(
            dict(
                campaign_id=campaign.id,
                kind="campaign.dispatched",
                level="info",
                message=f"“{name}” started sending to {len(audience_contacts)} recipients in {AUDIENCE_LABELS[audience]}",
                created_at=dispatched,
            )
        )

        recipient_ids = session.scalars(
            insert(CampaignRecipient).returning(CampaignRecipient.id, sort_by_parameter_order=True),
            [
                dict(
                    campaign_id=campaign.id,
                    contact_id=c.id,
                    name=c.name,
                    email=c.email,
                    status="pending",
                    created_at=dispatched,
                    updated_at=dispatched,
                )
                for c in audience_contacts
            ],
        ).all()
        recipients = list(zip(recipient_ids, audience_contacts))

        run_specs = [("initial", recipients)]
        finished_at = dispatched
        outcomes: dict[int, tuple[str, int, str | None, datetime]] = {}
        for run_number, (kind, members) in enumerate(run_specs, start=1):
            run_start = dispatched if kind == "initial" else finished_at + timedelta(hours=2)
            run = DeliveryRun(campaign_id=campaign.id, run_number=run_number, kind=kind, status="finished", job_count=len(members), created_at=run_start)
            session.add(run)
            session.flush()
            if kind == "manual_retry":
                events.append(
                    dict(
                        campaign_id=campaign.id,
                        kind="campaign.retry_started",
                        level="info",
                        message=f"Retrying {len(members)} failed deliveries for “{name}”",
                        created_at=run_start,
                    )
                )
            attempts_rows = []
            for position, (recipient_id, contact) in enumerate(members):
                prior = outcomes.get(recipient_id, (None, 0, None, run_start))[1]
                start = run_start + timedelta(seconds=position * 0.45)
                moment = start
                status, error = "failed", None
                job_attempts = 0
                for attempt in range(1, max_attempts + 1):
                    job_attempts = attempt
                    result = simulate(campaign.id, contact.id, contact.email, prior + attempt)
                    attempts_rows.append((attempt, result, moment))
                    if result.success:
                        status, error = "delivered", None
                        break
                    error = result.error
                    if attempt < max_attempts:
                        events.append(
                            dict(
                                campaign_id=campaign.id,
                                recipient_id=recipient_id,
                                kind="delivery.retry_scheduled",
                                level="warning",
                                message=f"Delivery to {contact.email} failed (attempt {attempt} of {max_attempts}); retrying in {settings.retry_delay_for(attempt)}s",
                                created_at=moment + timedelta(seconds=0.8),
                            )
                        )
                        moment += timedelta(seconds=settings.retry_delay_for(attempt) + 1)
                done = moment + timedelta(seconds=0.8)
                job_id = session.scalar(
                    insert(DeliveryJob)
                    .values(
                        run_id=run.id,
                        campaign_id=campaign.id,
                        recipient_id=recipient_id,
                        status=status,
                        attempts=job_attempts,
                        max_attempts=max_attempts,
                        last_error=error,
                        first_started_at=start,
                        last_started_at=moment,
                        finished_at=done,
                        created_at=run_start,
                        updated_at=done,
                    )
                    .returning(DeliveryJob.id)
                )
                session.execute(
                    insert(DeliveryAttempt),
                    [
                        dict(
                            job_id=job_id,
                            recipient_id=recipient_id,
                            campaign_id=campaign.id,
                            attempt_number=n,
                            outcome="success" if r.success else "failure",
                            error=r.error,
                            started_at=t,
                            finished_at=t + timedelta(seconds=0.8),
                        )
                        for n, r, t in attempts_rows
                    ],
                )
                attempts_rows.clear()
                events.append(
                    dict(
                        campaign_id=campaign.id,
                        recipient_id=recipient_id,
                        kind="delivery.delivered" if status == "delivered" else "delivery.failed",
                        level="success" if status == "delivered" else "error",
                        message=(
                            f"Delivered “{name}” to {contact.email}"
                            if status == "delivered"
                            else f"Could not deliver to {contact.email} after {job_attempts} attempts: {error}"
                        ),
                        created_at=done,
                    )
                )
                outcomes[recipient_id] = (status, prior + job_attempts, error, done)
                finished_at = max(finished_at, done)
            run.finished_at = finished_at
            if kind == "initial" and index in data.HISTORY_WITH_MANUAL_RETRY:
                failed = [(rid, c) for rid, c in members if outcomes[rid][0] == "failed"]
                if failed:
                    run_specs.append(("manual_retry", failed))

        counts = {"delivered": 0, "failed": 0, "skipped": 0}
        for recipient_id, (status, total_attempts, error, done) in outcomes.items():
            counts[status] += 1
            session.execute(
                text(
                    "UPDATE campaign_recipients SET status = :s, attempt_count = :a, last_error = :e, finished_at = :f, updated_at = :f WHERE id = :id"
                ),
                {"s": status, "a": total_attempts, "e": error, "f": done, "id": recipient_id},
            )
        campaign.status = "completed"
        campaign.recipient_count = len(recipients)
        campaign.completed_at = finished_at
        campaign.updated_at = finished_at
        parts = [f"{counts['delivered']} delivered"] + ([f"{counts['failed']} failed"] if counts["failed"] else [])
        campaign.status_note = ", ".join(parts)
        events.append(
            dict(
                campaign_id=campaign.id,
                kind="campaign.completed",
                level="warning" if counts["failed"] else "success",
                message=f"“{name}” finished sending: {campaign.status_note}",
                created_at=finished_at,
            )
        )
        session.execute(insert(ActivityEvent), [{"recipient_id": None, **e} for e in events])


def seed(session: Session) -> bool:
    """Seed demo data once. Returns True if data was written."""
    session.execute(text("SELECT pg_advisory_xact_lock(:id)"), {"id": ADVISORY_LOCK_ID})
    if is_seeded(session):
        log.info("demo data already present; skipping seed")
        return False

    settings = get_settings()
    now = utcnow()
    rng = random.Random(20261019)

    session.execute(
        text(
            "INSERT INTO contacts (name, email, company, segment, subscribed, unsubscribed_at, created_at, updated_at) "
            "VALUES (:name, :email, :company, :segment, :subscribed, :unsubscribed_at, :created_at, :updated_at) "
            "ON CONFLICT (lower(email)) DO NOTHING"
        ),
        _contacts(rng, now),
    )
    contacts = list(session.scalars(select(Contact).order_by(Contact.id)))
    _seed_history(session, contacts, now)

    for index, (name, subject, body, audience) in enumerate(data.DRAFTS):
        created = now - timedelta(days=2 - index, hours=3)
        draft = Campaign(name=name, subject=subject, body=body + data.SIGNATURE, audience=audience, status="draft", created_at=created, updated_at=created)
        session.add(draft)
        session.flush()
        session.add(ActivityEvent(campaign_id=draft.id, kind="campaign.created", message=f"“{name}” created", created_at=created))

    name, subject, body, audience = data.SCHEDULED
    scheduled_at = floor_minute(now) + timedelta(minutes=settings.demo_schedule_offset_minutes)
    scheduled = Campaign(
        name=name, subject=subject, body=body + data.SIGNATURE, audience=audience, status="scheduled", scheduled_at=scheduled_at
    )
    session.add(scheduled)
    session.flush()
    session.add(ActivityEvent(campaign_id=scheduled.id, kind="campaign.created", message=f"“{name}” created", created_at=now))
    session.add(
        ActivityEvent(
            campaign_id=scheduled.id,
            kind="campaign.scheduled",
            message=f"“{name}” scheduled for {AUDIENCE_LABELS[audience]}",
            created_at=now,
        )
    )

    session.add(AppMeta(key=SEED_KEY, value=SEED_VERSION))
    session.flush()
    log.info(
        "seeded demo data",
        extra={"contacts": len(contacts), "campaigns": len(data.HISTORY) + len(data.DRAFTS) + 1, "scheduled_at": scheduled_at.isoformat()},
    )
    return True


TABLES = (
    "activity_events, outbox, delivery_attempts, delivery_jobs, delivery_runs, campaign_recipients, "
    "campaigns, contacts, worker_heartbeats, cron_runs, app_meta"
)


def wipe(session: Session) -> None:
    """Destructive: remove every demo and user record."""
    session.execute(text(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE"))
