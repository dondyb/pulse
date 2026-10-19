"""The API's connection to NATS, used to publish Send Now and retry jobs immediately.

Publishing here is best effort: the outbox rows are already committed, so if the
broker is unavailable the cron task publishes them on its next run.
"""

import asyncio
import logging
import time

from nats.aio.client import Client

from app.queue.nats_client import connect, make_publisher
from app.services import outbox

log = logging.getLogger("pulse.api.queue")


class QueueClient:
    def __init__(self) -> None:
        self._nc: Client | None = None
        self._lock = asyncio.Lock()
        self._retry_after = 0.0  # back off after a failed connect so requests stay fast

    @property
    def connected(self) -> bool:
        return self._nc is not None and self._nc.is_connected

    async def ensure_connected(self) -> bool:
        return await self._client() is not None

    async def _client(self) -> Client | None:
        async with self._lock:
            if self._nc is not None and not self._nc.is_closed:
                return self._nc if self._nc.is_connected else None
            if time.monotonic() < self._retry_after:
                return None
            try:
                self._nc = await connect(name="pulse-api")
            except Exception as exc:  # noqa: BLE001
                log.warning("nats unavailable", extra={"error": type(exc).__name__})
                self._nc = None
                self._retry_after = time.monotonic() + 15
            return self._nc

    async def publish_campaign(self, campaign_id: int) -> bool:
        nc = await self._client()
        if nc is None:
            return False
        result = await outbox.flush(make_publisher(nc.jetstream()), campaign_id=campaign_id, max_seconds=10)
        if result.error:
            log.warning("immediate publish incomplete; cron will retry", extra={"campaign_id": campaign_id, "error": result.error})
            return False
        log.info("published campaign jobs", extra={"campaign_id": campaign_id, "published": result.published})
        return True

    async def close(self) -> None:
        if self._nc is not None and not self._nc.is_closed:
            try:
                await self._nc.drain()
            except Exception:  # noqa: BLE001
                pass
