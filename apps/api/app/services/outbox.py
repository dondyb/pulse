"""Outbox relay: publishes pending outbox rows to the queue.

Rows are claimed with a short lease (so concurrent relays never publish the same
row at the same time) and marked published only after the broker acknowledges.
A crash between publish and mark leaves the row pending; it is republished once
the lease expires. JetStream deduplicates by message id within its window and
the consumer is idempotent, so duplicates are harmless.
"""

import asyncio
import json
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import session_scope
from app.models import OutboxMessage
from app.timeutil import utcnow

log = logging.getLogger("pulse.outbox")

Publisher = Callable[[str, bytes, str], Awaitable[None]]


@dataclass
class ClaimedMessage:
    id: int
    message_id: str
    subject: str
    payload: dict


@dataclass
class FlushResult:
    published: int = 0
    error: str | None = None


def claim_batch(session: Session, limit: int, campaign_id: int | None = None) -> list[ClaimedMessage]:
    now = utcnow()
    lease_until = now + timedelta(seconds=get_settings().outbox_lease_seconds)
    campaign_filter = "AND (payload->>'campaign_id')::bigint = :campaign_id" if campaign_id is not None else ""
    rows = session.execute(
        text(
            f"""
            UPDATE outbox SET lease_until = :lease_until, publish_attempts = publish_attempts + 1
            WHERE id IN (
                SELECT id FROM outbox
                WHERE status = 'pending' AND available_at <= :now
                  AND (lease_until IS NULL OR lease_until < :now)
                  {campaign_filter}
                ORDER BY available_at, id
                LIMIT :limit
                FOR UPDATE SKIP LOCKED
            )
            RETURNING id, message_id, subject, payload
            """
        ),
        {"now": now, "lease_until": lease_until, "limit": limit, "campaign_id": campaign_id},
    ).all()
    return sorted((ClaimedMessage(r.id, r.message_id, r.subject, r.payload) for r in rows), key=lambda m: m.id)


def mark_published(session: Session, ids: list[int]) -> None:
    if ids:
        session.execute(
            text(
                "UPDATE outbox SET status = 'published', published_at = :now, lease_until = NULL, last_error = NULL "
                "WHERE id = ANY(:ids) AND status = 'pending'"
            ),
            {"now": utcnow(), "ids": ids},
        )


def release(session: Session, ids: list[int], error: str) -> None:
    if ids:
        session.execute(
            text("UPDATE outbox SET lease_until = NULL, last_error = :error WHERE id = ANY(:ids) AND status = 'pending'"),
            {"ids": ids, "error": error[:300]},
        )


def pending_count(session: Session) -> int:
    return session.scalar(select(func.count()).select_from(OutboxMessage).where(OutboxMessage.status == "pending")) or 0


def _claim(limit: int, campaign_id: int | None) -> list[ClaimedMessage]:
    with session_scope() as session:
        return claim_batch(session, limit, campaign_id)


def _mark(ids: list[int]) -> None:
    with session_scope() as session:
        mark_published(session, ids)


def _release(ids: list[int], error: str) -> None:
    with session_scope() as session:
        release(session, ids, error)


async def flush(
    publish: Publisher,
    *,
    batch_size: int = 200,
    max_messages: int | None = None,
    max_seconds: float | None = None,
    campaign_id: int | None = None,
) -> FlushResult:
    """Publish pending outbox rows until none are left or a bound is reached.

    Stops at the first publish failure and leaves the remaining rows pending.
    """
    result = FlushResult()
    started = time.monotonic()
    while True:
        if max_seconds is not None and time.monotonic() - started > max_seconds:
            break
        limit = batch_size
        if max_messages is not None:
            limit = min(limit, max_messages - result.published)
            if limit <= 0:
                break
        batch = await asyncio.to_thread(_claim, limit, campaign_id)
        if not batch:
            break
        done: list[int] = []
        try:
            for message in batch:
                await publish(message.subject, json.dumps(message.payload).encode(), message.message_id)
                done.append(message.id)
        except Exception as exc:  # noqa: BLE001 - any broker failure leaves rows pending
            result.error = f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__
            await asyncio.to_thread(_mark, done)
            await asyncio.to_thread(_release, [m.id for m in batch if m.id not in done], result.error)
            result.published += len(done)
            log.warning("outbox publish failed", extra={"published": result.published, "error": result.error})
            return result
        await asyncio.to_thread(_mark, done)
        result.published += len(done)
    return result
