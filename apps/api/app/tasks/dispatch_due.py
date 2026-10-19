"""One-shot cron task: `python -m app.tasks.dispatch_due`.

1. Record the start of this run.
2. Claim and dispatch due scheduled campaigns (one transaction each, SKIP LOCKED).
3. Publish pending outbox rows to NATS, including leftovers from Send Now.
4. Record the result and exit (nonzero on operational failure).

Safe to run repeatedly or concurrently: claiming uses row locks, outbox rows are
leased, and the worker is idempotent. Work per invocation is bounded.
"""

import asyncio
import logging
import sys
import time
from datetime import timedelta

from sqlalchemy import text

from app.config import get_settings
from app.db import session_scope
from app.logging import configure_logging
from app.models import CronRun
from app.queue.nats_client import connect, make_publisher
from app.services import outbox
from app.services.dispatch import dispatch_next_due
from app.timeutil import utcnow

log = logging.getLogger("pulse.cron")


def _start_run() -> int:
    with session_scope() as session:
        # A run that never finished (killed container, host sleep) is marked failed.
        session.execute(
            text(
                "UPDATE cron_runs SET status = 'failed', finished_at = now(), "
                "error = 'Run did not finish (process exited unexpectedly)' "
                "WHERE status = 'running' AND started_at < :cutoff"
            ),
            {"cutoff": utcnow() - timedelta(minutes=10)},
        )
        run = CronRun(task="dispatch_due", status="running", started_at=utcnow())
        session.add(run)
        session.flush()
        return run.id


def _finish_run(run_id: int, *, dispatched: int, published: int, errors: list[str]) -> int:
    with session_scope() as session:
        pending = outbox.pending_count(session)
        run = session.get(CronRun, run_id)
        run.finished_at = utcnow()
        run.campaigns_dispatched = dispatched
        run.outbox_published = published
        run.outbox_pending = pending
        run.status = "failed" if errors else "success"
        run.error = "; ".join(errors)[:500] if errors else None
        return pending


async def _publish(max_seconds: float) -> outbox.FlushResult:
    settings = get_settings()
    nc = await connect(name="pulse-cron", reconnect=False)
    try:
        return await outbox.flush(
            make_publisher(nc.jetstream()),
            batch_size=100,
            max_messages=settings.cron_outbox_batch,
            max_seconds=max_seconds,
        )
    finally:
        await nc.close()


def run() -> int:
    settings = get_settings()
    started = time.monotonic()
    try:
        run_id = _start_run()
    except Exception as exc:  # noqa: BLE001
        log.error("cannot record cron run; database unavailable", extra={"error": type(exc).__name__})
        return 2

    errors: list[str] = []
    dispatched = 0
    try:
        while dispatched < settings.cron_campaign_batch and time.monotonic() - started < settings.cron_max_seconds:
            with session_scope() as session:
                result = dispatch_next_due(session)
            if result is None:
                break
            dispatched += 1
            log.info("dispatched scheduled campaign", extra={"campaign_id": result.campaign_id, "recipients": result.recipient_count})
    except Exception as exc:  # noqa: BLE001
        log.exception("dispatch failed")
        errors.append(f"Dispatch error: {type(exc).__name__}")

    published = 0
    remaining = max(settings.cron_max_seconds - (time.monotonic() - started), 5)
    try:
        result = asyncio.run(asyncio.wait_for(_publish(remaining), timeout=remaining + 5))
        published = result.published
        if result.error:
            errors.append(f"Queue publish failed: {result.error}")
    except Exception as exc:  # noqa: BLE001
        name = type(exc).__name__
        log.error("NATS unavailable; outbox records kept for the next run", extra={"error": name})
        errors.append(f"Queue unavailable ({name}); pending deliveries kept for the next run")

    try:
        pending = _finish_run(run_id, dispatched=dispatched, published=published, errors=errors)
    except Exception as exc:  # noqa: BLE001
        log.error("cannot record cron result", extra={"error": type(exc).__name__})
        return 2

    log.info(
        "cron run finished",
        extra={
            "run_id": run_id,
            "status": "failed" if errors else "success",
            "campaigns_dispatched": dispatched,
            "outbox_published": published,
            "outbox_pending": pending,
            "duration_ms": int((time.monotonic() - started) * 1000),
        },
    )
    return 1 if errors else 0


def main() -> None:
    configure_logging(get_settings().log_level, "cron")
    sys.exit(run())


if __name__ == "__main__":
    main()
