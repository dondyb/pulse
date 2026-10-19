"""Read models for the API: lists, detail views, dashboard metrics and job activity."""

from datetime import datetime, timedelta

from sqlalchemy import case, func, select, text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import (
    AUDIENCES,
    ActivityEvent,
    Campaign,
    CampaignRecipient,
    Contact,
    CronRun,
    DeliveryAttempt,
    DeliveryJob,
    DeliveryRun,
    WorkerHeartbeat,
)
from app.services import outbox
from app.services.dispatch import AUDIENCE_LABELS, audience_condition
from app.timeutil import display_tz, local_day_start, utcnow


def like_pattern(term: str) -> str:
    escaped = term.strip().lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def page_meta(total: int, page: int, page_size: int) -> dict:
    return {"total": total, "page": page, "page_size": page_size, "pages": max((total + page_size - 1) // page_size, 1)}


# ---------------------------------------------------------------- audiences


def audience_counts(session: Session) -> dict[str, int]:
    return {
        audience: session.scalar(select(func.count()).select_from(Contact).where(audience_condition(audience))) or 0
        for audience in AUDIENCES
    }


# ---------------------------------------------------------------- campaigns

EMPTY_COUNTS = {"pending": 0, "delivered": 0, "failed": 0, "skipped": 0, "total": 0}


def _counts_by_campaign(session: Session, ids: list[int]) -> dict[int, dict[str, int]]:
    if not ids:
        return {}
    rows = session.execute(
        select(CampaignRecipient.campaign_id, CampaignRecipient.status, func.count())
        .where(CampaignRecipient.campaign_id.in_(ids))
        .group_by(CampaignRecipient.campaign_id, CampaignRecipient.status)
    ).all()
    result: dict[int, dict[str, int]] = {}
    for campaign_id, status, count in rows:
        counts = result.setdefault(campaign_id, dict(EMPTY_COUNTS))
        counts[status] = count
        counts["total"] += count
    return result


def _active_runs(session: Session, ids: list[int]) -> set[int]:
    if not ids:
        return set()
    return set(
        session.scalars(select(DeliveryRun.campaign_id).where(DeliveryRun.campaign_id.in_(ids), DeliveryRun.status == "active"))
    )


def serialize_campaign(
    campaign: Campaign, counts: dict[str, int], estimates: dict[str, int], has_active_run: bool, now: datetime
) -> dict:
    terminal = counts["delivered"] + counts["failed"] + counts["skipped"]
    is_preview = campaign.status in ("draft", "scheduled")
    return {
        "id": campaign.id,
        "name": campaign.name,
        "subject": campaign.subject,
        "body": campaign.body,
        "audience": campaign.audience,
        "audience_label": AUDIENCE_LABELS[campaign.audience],
        "channel": campaign.channel,
        "status": campaign.status,
        "has_failures": campaign.status in ("completed", "processing") and counts["failed"] > 0,
        "status_note": campaign.status_note,
        "scheduled_at": campaign.scheduled_at,
        "dispatched_at": campaign.dispatched_at,
        "completed_at": campaign.completed_at,
        "cancelled_at": campaign.cancelled_at,
        "created_at": campaign.created_at,
        "updated_at": campaign.updated_at,
        "duplicated_from_id": campaign.duplicated_from_id,
        "recipient_count": estimates.get(campaign.audience, 0) if is_preview else campaign.recipient_count,
        "recipient_count_is_estimate": is_preview,
        "counts": counts,
        "progress": (terminal / counts["total"]) if counts["total"] else (1.0 if campaign.status == "completed" else 0.0),
        "awaiting_dispatch": campaign.status == "scheduled"
        and campaign.scheduled_at is not None
        and campaign.scheduled_at <= now,
        "can_edit": campaign.status == "draft",
        "can_cancel": campaign.status == "scheduled",
        "can_retry": campaign.status == "completed" and counts["failed"] > 0 and not has_active_run,
        "has_active_run": has_active_run,
    }


def serialize_campaigns(session: Session, campaigns: list[Campaign]) -> list[dict]:
    ids = [c.id for c in campaigns]
    counts = _counts_by_campaign(session, ids)
    active = _active_runs(session, ids)
    needs_estimate = any(c.status in ("draft", "scheduled") for c in campaigns)
    estimates = audience_counts(session) if needs_estimate else {}
    now = utcnow()
    return [serialize_campaign(c, counts.get(c.id, dict(EMPTY_COUNTS)), estimates, c.id in active, now) for c in campaigns]


def list_campaigns(session: Session, *, search: str, status: str | None, page: int, page_size: int) -> dict:
    query = select(Campaign)
    if search.strip():
        query = query.where(func.lower(Campaign.name).like(like_pattern(search), escape="\\"))
    if status == "completed_with_failures":
        failed_ids = select(CampaignRecipient.campaign_id).where(CampaignRecipient.status == "failed")
        query = query.where(Campaign.status == "completed", Campaign.id.in_(failed_ids))
    elif status:
        query = query.where(Campaign.status == status)
    total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = list(
        session.scalars(query.order_by(Campaign.created_at.desc(), Campaign.id.desc()).offset((page - 1) * page_size).limit(page_size))
    )
    return {"items": serialize_campaigns(session, rows), **page_meta(total, page, page_size)}


def campaign_detail(session: Session, campaign: Campaign) -> dict:
    data = serialize_campaigns(session, [campaign])[0]
    runs = session.scalars(select(DeliveryRun).where(DeliveryRun.campaign_id == campaign.id).order_by(DeliveryRun.run_number))
    data["runs"] = [
        {
            "id": r.id,
            "run_number": r.run_number,
            "kind": r.kind,
            "status": r.status,
            "job_count": r.job_count,
            "created_at": r.created_at,
            "finished_at": r.finished_at,
        }
        for r in runs
    ]
    return data


def list_recipients(session: Session, campaign_id: int, *, status: str | None, search: str, page: int, page_size: int) -> dict:
    query = select(CampaignRecipient).where(CampaignRecipient.campaign_id == campaign_id)
    if status:
        query = query.where(CampaignRecipient.status == status)
    if search.strip():
        pattern = like_pattern(search)
        query = query.where(
            func.lower(CampaignRecipient.name + " " + CampaignRecipient.email).like(pattern, escape="\\")
        )
    total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = list(
        session.scalars(
            query.order_by(
                case((CampaignRecipient.status == "failed", 0), (CampaignRecipient.status == "pending", 1), else_=2),
                CampaignRecipient.updated_at.desc(),
                CampaignRecipient.id,
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    return {
        "items": [
            {
                "id": r.id,
                "contact_id": r.contact_id,
                "name": r.name,
                "email": r.email,
                "status": r.status,
                "attempt_count": r.attempt_count,
                "last_error": r.last_error,
                "finished_at": r.finished_at,
                "updated_at": r.updated_at,
            }
            for r in rows
        ],
        **page_meta(total, page, page_size),
    }


def recipient_attempts(session: Session, campaign_id: int, recipient_id: int) -> list[dict]:
    rows = session.execute(
        select(DeliveryAttempt, DeliveryRun.run_number)
        .join(DeliveryJob, DeliveryJob.id == DeliveryAttempt.job_id)
        .join(DeliveryRun, DeliveryRun.id == DeliveryJob.run_id)
        .where(DeliveryAttempt.campaign_id == campaign_id, DeliveryAttempt.recipient_id == recipient_id)
        .order_by(DeliveryAttempt.started_at, DeliveryAttempt.id)
    ).all()
    return [
        {
            "id": a.id,
            "run_number": run_number,
            "attempt_number": a.attempt_number,
            "outcome": a.outcome,
            "error": a.error,
            "started_at": a.started_at,
            "finished_at": a.finished_at,
        }
        for a, run_number in rows
    ]


def serialize_event(event: ActivityEvent, campaign_name: str | None) -> dict:
    return {
        "id": event.id,
        "kind": event.kind,
        "level": event.level,
        "message": event.message,
        "campaign_id": event.campaign_id,
        "campaign_name": campaign_name,
        "created_at": event.created_at,
    }


def list_activity(session: Session, *, campaign_id: int | None = None, limit: int = 20, milestones_only: bool = False) -> list[dict]:
    query = select(ActivityEvent, Campaign.name).outerjoin(Campaign, Campaign.id == ActivityEvent.campaign_id)
    if campaign_id is not None:
        query = query.where(ActivityEvent.campaign_id == campaign_id)
    if milestones_only:
        query = query.where(ActivityEvent.kind != "delivery.delivered")
    rows = session.execute(query.order_by(ActivityEvent.created_at.desc(), ActivityEvent.id.desc()).limit(limit)).all()
    return [serialize_event(e, name) for e, name in rows]


# ---------------------------------------------------------------- dashboard


def dashboard(session: Session) -> dict:
    settings = get_settings()
    now = utcnow()
    today_start = local_day_start(now)
    window_start = today_start - timedelta(days=6)

    delivered_today = session.scalar(
        select(func.count())
        .select_from(CampaignRecipient)
        .where(CampaignRecipient.status == "delivered", CampaignRecipient.finished_at >= today_start)
    )
    outcome_rows = dict(
        session.execute(
            select(CampaignRecipient.status, func.count())
            .where(CampaignRecipient.status.in_(("delivered", "failed")), CampaignRecipient.finished_at >= window_start)
            .group_by(CampaignRecipient.status)
        ).all()
    )
    delivered_7d = outcome_rows.get("delivered", 0)
    failed_7d = outcome_rows.get("failed", 0)
    decided = delivered_7d + failed_7d
    pending = session.scalar(
        select(func.count())
        .select_from(CampaignRecipient)
        .join(Campaign, Campaign.id == CampaignRecipient.campaign_id)
        .where(CampaignRecipient.status == "pending", Campaign.status == "processing")
    )
    scheduled = session.scalar(select(func.count()).select_from(Campaign).where(Campaign.status == "scheduled"))

    tz = settings.display_timezone
    day_rows = session.execute(
        text(
            """
            SELECT (finished_at AT TIME ZONE :tz)::date AS day, status, count(*) AS n
            FROM campaign_recipients
            WHERE finished_at >= :start AND status IN ('delivered', 'failed')
            GROUP BY 1, 2
            """
        ),
        {"tz": tz, "start": window_start},
    ).all()
    by_day: dict[str, dict[str, int]] = {}
    for day, status, n in day_rows:
        by_day.setdefault(day.isoformat(), {})[status] = n
    first_local_day = window_start.astimezone(display_tz()).date()
    volume = []
    for offset in range(7):
        day = (first_local_day + timedelta(days=offset)).isoformat()
        volume.append({"date": day, "delivered": by_day.get(day, {}).get("delivered", 0), "failed": by_day.get(day, {}).get("failed", 0)})

    status_rows = dict(session.execute(select(Campaign.status, func.count()).group_by(Campaign.status)).all())
    with_failures = session.scalar(
        select(func.count(func.distinct(CampaignRecipient.campaign_id)))
        .join(Campaign, Campaign.id == CampaignRecipient.campaign_id)
        .where(Campaign.status == "completed", CampaignRecipient.status == "failed")
    )
    breakdown = [
        {"status": "draft", "label": "Draft", "count": status_rows.get("draft", 0)},
        {"status": "scheduled", "label": "Scheduled", "count": status_rows.get("scheduled", 0)},
        {"status": "processing", "label": "Sending", "count": status_rows.get("processing", 0)},
        {"status": "completed", "label": "Completed", "count": status_rows.get("completed", 0) - with_failures},
        {"status": "completed_with_failures", "label": "Completed with failures", "count": with_failures},
        {"status": "cancelled", "label": "Cancelled", "count": status_rows.get("cancelled", 0)},
    ]

    recent = list(session.scalars(select(Campaign).order_by(Campaign.created_at.desc(), Campaign.id.desc()).limit(6)))
    next_scheduled = session.scalars(
        select(Campaign).where(Campaign.status == "scheduled").order_by(Campaign.scheduled_at, Campaign.id).limit(1)
    ).first()

    return {
        "generated_at": now,
        "timezone": tz,
        "metrics": {
            "delivered_today": {
                "value": delivered_today,
                "period_start": today_start,
                "definition": "Recipients whose email was delivered since midnight (Asia/Jakarta).",
            },
            "success_rate": {
                "value": (delivered_7d / decided) if decided else None,
                "delivered": delivered_7d,
                "failed": failed_7d,
                "period_start": window_start,
                "definition": "Delivered ÷ (delivered + failed) unique recipients whose final outcome was recorded in the last 7 days. Skipped and still-pending recipients are excluded.",
            },
            "pending_deliveries": {
                "value": pending,
                "definition": "Recipients in campaigns that are currently sending and have not reached a final outcome.",
            },
            "scheduled_campaigns": {"value": scheduled, "definition": "Campaigns waiting for their scheduled send time."},
        },
        "volume": volume,
        "status_breakdown": breakdown,
        "recent_campaigns": serialize_campaigns(session, recent),
        "next_scheduled": serialize_campaigns(session, [next_scheduled])[0] if next_scheduled else None,
        "activity": list_activity(session, limit=12),
    }


# ---------------------------------------------------------------- job activity


def list_jobs(session: Session, *, status: str | None, campaign_id: int | None, search: str, page: int, page_size: int) -> dict:
    query = (
        select(DeliveryJob, CampaignRecipient, Campaign.name, DeliveryRun.run_number, DeliveryRun.kind)
        .join(CampaignRecipient, CampaignRecipient.id == DeliveryJob.recipient_id)
        .join(Campaign, Campaign.id == DeliveryJob.campaign_id)
        .join(DeliveryRun, DeliveryRun.id == DeliveryJob.run_id)
    )
    if status:
        query = query.where(DeliveryJob.status == status)
    if campaign_id:
        query = query.where(DeliveryJob.campaign_id == campaign_id)
    if search.strip():
        query = query.where(func.lower(CampaignRecipient.email).like(like_pattern(search), escape="\\"))
    total = session.scalar(select(func.count()).select_from(query.with_only_columns(DeliveryJob.id).subquery())) or 0
    rows = session.execute(
        query.order_by(DeliveryJob.updated_at.desc(), DeliveryJob.id.desc()).offset((page - 1) * page_size).limit(page_size)
    ).all()
    items = [
        {
            "id": job.id,
            "campaign_id": job.campaign_id,
            "campaign_name": campaign_name,
            "run_number": run_number,
            "run_kind": run_kind,
            "recipient_id": recipient.id,
            "recipient_name": recipient.name,
            "recipient_email": recipient.email,
            "status": job.status,
            "attempts": job.attempts,
            "max_attempts": job.max_attempts,
            "last_error": job.last_error,
            "next_attempt_at": job.next_attempt_at if job.status == "retrying" else None,
            "locked_by": job.locked_by,
            "first_started_at": job.first_started_at,
            "last_started_at": job.last_started_at,
            "finished_at": job.finished_at,
            "created_at": job.created_at,
            "updated_at": job.updated_at,
        }
        for job, recipient, campaign_name, run_number, run_kind in rows
    ]
    return {"items": items, **page_meta(total, page, page_size)}


def _cron(run: CronRun | None) -> dict | None:
    if run is None:
        return None
    return {
        "id": run.id,
        "status": run.status,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "duration_ms": int((run.finished_at - run.started_at).total_seconds() * 1000) if run.finished_at else None,
        "campaigns_dispatched": run.campaigns_dispatched,
        "outbox_published": run.outbox_published,
        "outbox_pending": run.outbox_pending,
        "error": run.error,
    }


def job_summary(session: Session) -> dict:
    settings = get_settings()
    now = utcnow()
    counts = {s: 0 for s in ("queued", "processing", "retrying", "delivered", "failed", "skipped")}
    counts.update(dict(session.execute(select(DeliveryJob.status, func.count()).group_by(DeliveryJob.status)).all()))

    stale_after = timedelta(seconds=settings.worker_heartbeat_seconds * 3)
    workers = [
        {
            "worker_id": w.worker_id,
            "hostname": w.hostname,
            "status": w.status if (w.status == "stopped" or now - w.last_seen_at <= stale_after) else "unresponsive",
            "online": w.status == "running" and now - w.last_seen_at <= stale_after,
            "concurrency": w.concurrency,
            "jobs_processed": w.jobs_processed,
            "started_at": w.started_at,
            "last_seen_at": w.last_seen_at,
        }
        for w in session.scalars(
            select(WorkerHeartbeat)
            .where(WorkerHeartbeat.last_seen_at >= now - timedelta(hours=24))
            .order_by(WorkerHeartbeat.last_seen_at.desc())
            .limit(10)
        )
    ]
    last_run = session.scalars(select(CronRun).order_by(CronRun.started_at.desc(), CronRun.id.desc()).limit(1)).first()
    last_success = session.scalars(
        select(CronRun).where(CronRun.status == "success").order_by(CronRun.started_at.desc()).limit(1)
    ).first()
    recent_runs = session.scalars(select(CronRun).order_by(CronRun.started_at.desc(), CronRun.id.desc()).limit(10))
    return {
        "counts": counts,
        "workers": workers,
        "cron": {
            "schedule": "* * * * * (every minute)",
            "last_run": _cron(last_run),
            "last_success": _cron(last_success),
            "recent_runs": [_cron(r) for r in recent_runs],
        },
        "outbox_pending": outbox.pending_count(session),
        "settings": {
            "worker_concurrency": settings.worker_concurrency,
            "max_attempts": settings.delivery_max_attempts,
            "retry_delays_seconds": settings.retry_delays,
            "sim_delay_ms": [settings.sim_delay_min_ms, settings.sim_delay_max_ms],
        },
    }
