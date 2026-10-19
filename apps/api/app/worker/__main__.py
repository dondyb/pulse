"""Delivery worker: `python -m app.worker`.

Consumes job messages from a durable JetStream pull consumer. Each message names
a persisted delivery job; the job row (not the message) is the source of truth,
so redelivered or duplicated messages are harmless. Messages are acknowledged
only after the outcome is committed. Retries are delayed with NAK+delay, so no
worker slot waits on a retry.
"""

import asyncio
import json
import logging
import os
import random
import signal
import socket

import nats.errors
from sqlalchemy import text

from app.config import get_settings
from app.db import session_scope
from app.logging import configure_logging
from app.queue.nats_client import connect, ensure_stream
from app.services.delivery import Claim, Decision, begin_attempt, complete_attempt
from app.services.simulation import simulate

log = logging.getLogger("pulse.worker")


class Worker:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.worker_id = f"worker-{socket.gethostname()}"
        self.stopping = asyncio.Event()
        self.processed = 0
        self.inflight: set[asyncio.Task] = set()

    # ------------------------------------------------------------ persistence

    def _heartbeat(self, status: str = "running") -> None:
        with session_scope() as session:
            session.execute(
                text(
                    """
                    INSERT INTO worker_heartbeats (worker_id, hostname, status, concurrency, jobs_processed, started_at, last_seen_at)
                    VALUES (:id, :host, :status, :concurrency, :processed, now(), now())
                    ON CONFLICT (worker_id) DO UPDATE SET status = :status, concurrency = :concurrency,
                        jobs_processed = :processed, last_seen_at = now(),
                        started_at = CASE WHEN worker_heartbeats.status = 'stopped' THEN now() ELSE worker_heartbeats.started_at END
                    """
                ),
                {
                    "id": self.worker_id,
                    "host": socket.gethostname(),
                    "status": status,
                    "concurrency": self.settings.worker_concurrency,
                    "processed": self.processed,
                },
            )

    def _begin(self, job_id: int) -> Claim | Decision:
        with session_scope() as session:
            return begin_attempt(session, job_id, self.worker_id)

    def _complete(self, claim: Claim, result) -> Decision:
        with session_scope() as session:
            return complete_attempt(session, claim, result, self.worker_id)

    # ------------------------------------------------------------ messages

    async def _respond(self, msg, decision: Decision, job_id: int) -> None:
        if decision.action == "ack":
            await msg.ack()
        else:
            await msg.nak(delay=decision.delay)
        log.debug("job message handled", extra={"job_id": job_id, "action": decision.action, "reason": decision.reason})

    async def handle(self, msg) -> None:
        try:
            job_id = int(json.loads(msg.data)["job_id"])
        except (ValueError, KeyError, TypeError):
            log.error("discarding malformed message", extra={"subject": msg.subject})
            await msg.term()
            return
        try:
            outcome = await asyncio.to_thread(self._begin, job_id)
            if isinstance(outcome, Decision):
                await self._respond(msg, outcome, job_id)
                return
            claim = outcome
            delay_ms = random.uniform(self.settings.sim_delay_min_ms, self.settings.sim_delay_max_ms)
            await asyncio.sleep(delay_ms / 1000)
            result = simulate(claim.campaign_id, claim.contact_id, claim.email, claim.overall_attempt)
            decision = await asyncio.to_thread(self._complete, claim, result)
            self.processed += 1
            log.info(
                "delivery attempt finished",
                extra={
                    "job_id": job_id,
                    "campaign_id": claim.campaign_id,
                    "attempt": claim.attempt_number,
                    "success": result.success,
                    "next": decision.reason,
                },
            )
            await self._respond(msg, decision, job_id)
        except Exception:
            log.exception("job processing error; message will be redelivered", extra={"job_id": job_id})
            try:
                await msg.nak(delay=5)
            except Exception:  # noqa: BLE001
                pass

    # ------------------------------------------------------------ loops

    async def heartbeat_loop(self) -> None:
        while not self.stopping.is_set():
            try:
                await asyncio.to_thread(self._heartbeat)
            except Exception as exc:  # noqa: BLE001
                log.warning("heartbeat failed", extra={"error": type(exc).__name__})
            try:
                await asyncio.wait_for(self.stopping.wait(), timeout=self.settings.worker_heartbeat_seconds)
            except asyncio.TimeoutError:
                pass

    async def connect(self):
        delay = 1.0
        while not self.stopping.is_set():
            try:
                nc = await connect(name=self.worker_id)
                js = nc.jetstream()
                await ensure_stream(js)
                return nc, js
            except Exception as exc:  # noqa: BLE001
                log.warning("waiting for NATS", extra={"error": type(exc).__name__, "retry_in": delay})
                try:
                    await asyncio.wait_for(self.stopping.wait(), timeout=delay)
                except asyncio.TimeoutError:
                    pass
                delay = min(delay * 2, 15)
        return None, None

    async def run(self) -> None:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, self.stopping.set)

        heartbeat = asyncio.create_task(self.heartbeat_loop())
        nc, js = await self.connect()
        if nc is None:
            await heartbeat
            return
        sub = await js.pull_subscribe(
            self.settings.nats_subject, durable=self.settings.nats_consumer, stream=self.settings.nats_stream
        )
        log.info(
            "worker started",
            extra={"worker_id": self.worker_id, "concurrency": self.settings.worker_concurrency, "pid": os.getpid()},
        )

        while not self.stopping.is_set():
            free = self.settings.worker_concurrency - len(self.inflight)
            if free <= 0:
                await asyncio.wait(self.inflight, return_when=asyncio.FIRST_COMPLETED, timeout=1)
                continue
            # Race the fetch against shutdown so SIGTERM is honoured promptly.
            # Messages fetched but never handled are redelivered after ack_wait.
            fetch = asyncio.ensure_future(sub.fetch(free, timeout=2))
            stop = asyncio.ensure_future(self.stopping.wait())
            await asyncio.wait({fetch, stop}, return_when=asyncio.FIRST_COMPLETED)
            stop.cancel()
            if not fetch.done():
                fetch.cancel()
                break
            try:
                messages = fetch.result()
            except nats.errors.TimeoutError:
                continue
            except Exception as exc:  # noqa: BLE001
                log.warning("fetch failed", extra={"error": type(exc).__name__})
                await asyncio.sleep(1)
                continue
            for msg in messages:
                task = asyncio.create_task(self.handle(msg))
                self.inflight.add(task)
                task.add_done_callback(self.inflight.discard)

        log.info("shutting down; finishing in-flight jobs", extra={"in_flight": len(self.inflight)})
        if self.inflight:
            await asyncio.wait(self.inflight, timeout=20)
        await heartbeat
        try:
            await asyncio.to_thread(self._heartbeat, "stopped")
        except Exception:  # noqa: BLE001
            pass
        # Unacked messages are redelivered by JetStream; don't let drain block shutdown.
        try:
            await sub.unsubscribe()
            await asyncio.wait_for(nc.drain(), timeout=5)
        except Exception:  # noqa: BLE001
            await nc.close()
        log.info("worker stopped", extra={"processed": self.processed})


def main() -> None:
    configure_logging(get_settings().log_level, "worker")
    asyncio.run(Worker().run())


if __name__ == "__main__":
    main()
