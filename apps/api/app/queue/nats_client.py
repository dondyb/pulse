"""NATS JetStream connection helpers."""

import asyncio
import logging

import nats
from nats.aio.client import Client
from nats.js import JetStreamContext
from nats.js.api import AckPolicy, ConsumerConfig, DeliverPolicy, RetentionPolicy, StorageType, StreamConfig
from nats.js.errors import NotFoundError

from app.config import get_settings

log = logging.getLogger("pulse.queue")


async def _on_error(exc: Exception) -> None:
    # Replaces nats-py's default handler, which logs a full traceback per retry.
    log.warning("nats connection error", extra={"error": f"{type(exc).__name__}: {exc}"[:200]})


async def _on_disconnect() -> None:
    # Also fires on a normal close; a lost connection is retried automatically.
    log.info("nats disconnected")


async def _on_reconnect() -> None:
    log.info("nats reconnected")


async def connect(*, name: str, reconnect: bool = True) -> Client:
    settings = get_settings()
    options = dict(
        servers=[settings.nats_url],
        name=name,
        connect_timeout=settings.nats_connect_timeout_seconds,
        error_cb=_on_error,
        disconnected_cb=_on_disconnect,
        reconnected_cb=_on_reconnect,
    )
    if settings.nats_user and "@" not in settings.nats_url:
        options.update(user=settings.nats_user, password=settings.nats_password or "")
    if reconnect:
        # Once connected, reconnect forever after broker restarts.
        options.update(max_reconnect_attempts=-1, reconnect_time_wait=2)
    else:
        options.update(allow_reconnect=False, max_reconnect_attempts=0)
    # nats-py can keep retrying the *initial* connection indefinitely; callers
    # must fail fast instead (cron exits, the API falls back to the outbox).
    return await asyncio.wait_for(nats.connect(**options), timeout=settings.nats_connect_timeout_seconds * 2)


async def ensure_stream(js: JetStreamContext) -> None:
    """Create the durable work-queue stream and consumer if they don't exist."""
    settings = get_settings()
    config = StreamConfig(
        name=settings.nats_stream,
        subjects=[settings.nats_subject],
        retention=RetentionPolicy.WORK_QUEUE,
        storage=StorageType.FILE,
        duplicate_window=120.0,
        max_age=7 * 24 * 3600.0,
    )
    try:
        await js.stream_info(settings.nats_stream)
    except NotFoundError:
        await js.add_stream(config)
        log.info("created stream", extra={"stream": settings.nats_stream})

    consumer = ConsumerConfig(
        durable_name=settings.nats_consumer,
        ack_policy=AckPolicy.EXPLICIT,
        deliver_policy=DeliverPolicy.ALL,
        ack_wait=float(settings.job_lease_seconds),
        max_deliver=-1,
        max_ack_pending=1000,
        filter_subject=settings.nats_subject,
    )
    try:
        await js.consumer_info(settings.nats_stream, settings.nats_consumer)
    except NotFoundError:
        await js.add_consumer(settings.nats_stream, consumer)
        log.info("created consumer", extra={"consumer": settings.nats_consumer})


def make_publisher(js: JetStreamContext):
    async def publish(subject: str, data: bytes, message_id: str) -> None:
        await js.publish(subject, data, timeout=5, headers={"Nats-Msg-Id": message_id})

    return publish
