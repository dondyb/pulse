"""Tests run against a real PostgreSQL database (`<name>_test`), because the
behaviour under test depends on row locks, SKIP LOCKED and constraints."""

import os
import re

from sqlalchemy.engine import make_url

_base = make_url(os.environ.get("DATABASE_URL", "postgresql+psycopg://pulse:pulse@localhost:5432/pulse"))
TEST_URL = _base.set(database=f"{_base.database}_test")
os.environ["DATABASE_URL"] = TEST_URL.render_as_string(hide_password=False)

import pytest  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

from app.db import session_scope  # noqa: E402
from app.models import Campaign, Contact  # noqa: E402
from app.services.simulation import failures_before_success  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def database():
    admin = create_engine(_base.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        exists = conn.scalar(text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": TEST_URL.database})
        if not exists:
            assert re.fullmatch(r"[a-z0-9_]+", TEST_URL.database)
            conn.execute(text(f'CREATE DATABASE "{TEST_URL.database}"'))
    admin.dispose()
    from app.cli import migrate

    migrate()
    yield


@pytest.fixture(autouse=True)
def clean(database):
    from app.seed.seed import wipe

    with session_scope() as session:
        wipe(session)
    yield


_counter = {"n": 0}


def add_contact(session, *, segment="vip_customer", subscribed=True, email=None) -> Contact:
    _counter["n"] += 1
    n = _counter["n"]
    contact = Contact(
        name=f"Test Person {n}",
        email=email or f"person{n}@test.example",
        company="PT Uji Coba",
        segment=segment,
        subscribed=subscribed,
    )
    session.add(contact)
    session.flush()
    return contact


def add_campaign(session, *, audience="vip_customers", status="draft", scheduled_at=None, name="Test campaign") -> Campaign:
    campaign = Campaign(
        name=name, subject="Subject", body="Body", audience=audience, status=status, scheduled_at=scheduled_at
    )
    session.add(campaign)
    session.flush()
    return campaign


def add_contact_with_profile(session, campaign_id: int, failures: int | None, segment="vip_customer") -> Contact:
    """Create a contact whose simulated behaviour in `campaign_id` matches `failures`
    (attempts that fail before success; None = never succeeds). Non-matching
    candidates are parked in the `prospect` segment, outside the test audiences."""
    for _ in range(2000):
        contact = add_contact(session, segment="prospect")
        if failures_before_success(campaign_id, contact.id, contact.email) == failures:
            contact.segment = segment
            session.flush()
            return contact
    raise AssertionError("no contact with the requested profile")
