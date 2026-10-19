"""Operational commands.

    python -m app.cli init            # migrate, ensure queue stream, seed once (used by the init service)
    python -m app.cli reset --yes     # DESTRUCTIVE: delete all data, purge the queue, reseed
"""

import argparse
import asyncio
import logging
import sys
import time
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import text

from app.config import get_settings
from app.db import get_engine, session_scope
from app.logging import configure_logging
from app.queue.nats_client import connect, ensure_stream
from app.seed.seed import seed, wipe

log = logging.getLogger("pulse.cli")
MIGRATION_LOCK_ID = 74_210_000


def wait_for_database(timeout: float = 90) -> None:
    deadline = time.monotonic() + timeout
    while True:
        try:
            with get_engine().connect() as conn:
                conn.execute(text("SELECT 1"))
            return
        except Exception as exc:  # noqa: BLE001
            if time.monotonic() > deadline:
                raise
            log.info("waiting for database", extra={"error": type(exc).__name__})
            time.sleep(2)


def migrate() -> None:
    config = Config(str(Path(__file__).resolve().parent.parent / "alembic.ini"))
    config.set_main_option("script_location", str(Path(__file__).resolve().parent.parent / "alembic"))
    with get_engine().connect() as conn:
        # Serialize concurrent migrators; the lock is released when the connection closes.
        conn.execute(text("SELECT pg_advisory_lock(:id)"), {"id": MIGRATION_LOCK_ID})
        try:
            command.upgrade(config, "head")
        finally:
            conn.execute(text("SELECT pg_advisory_unlock(:id)"), {"id": MIGRATION_LOCK_ID})
            conn.commit()
    log.info("database migrations applied")


async def prepare_queue(purge: bool = False, timeout: float = 60) -> None:
    settings = get_settings()
    deadline = time.monotonic() + timeout
    while True:
        try:
            nc = await connect(name="pulse-init", reconnect=False)
            break
        except Exception as exc:  # noqa: BLE001
            if time.monotonic() > deadline:
                raise
            log.info("waiting for NATS", extra={"error": type(exc).__name__})
            await asyncio.sleep(2)
    try:
        js = nc.jetstream()
        await ensure_stream(js)
        if purge:
            await js.purge_stream(settings.nats_stream)
            log.info("queue stream purged", extra={"stream": settings.nats_stream})
    finally:
        await nc.close()
    log.info("queue stream ready", extra={"stream": settings.nats_stream})


def cmd_init(_: argparse.Namespace) -> int:
    wait_for_database()
    migrate()
    asyncio.run(prepare_queue())
    with session_scope() as session:
        seed(session)
    log.info("initialization complete")
    return 0


def cmd_reset(args: argparse.Namespace) -> int:
    if not args.yes:
        print("Refusing to reset without --yes. This deletes ALL contacts, campaigns and delivery history.", file=sys.stderr)
        return 2
    wait_for_database()
    migrate()
    with session_scope() as session:
        wipe(session)
        log.warning("all data deleted")
        seed(session)
    asyncio.run(prepare_queue(purge=True))
    log.info("reset complete")
    return 0


def main() -> None:
    configure_logging(get_settings().log_level, "cli")
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init", help="migrate, prepare the queue, seed demo data once").set_defaults(func=cmd_init)
    reset = sub.add_parser("reset", help="DESTRUCTIVE: delete all data and reseed")
    reset.add_argument("--yes", action="store_true", help="confirm deletion of all data")
    reset.set_defaults(func=cmd_reset)
    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
