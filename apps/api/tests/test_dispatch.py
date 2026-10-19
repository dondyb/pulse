"""Dispatch claiming, cron concurrency, and cancellation races."""

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app.db import get_sessionmaker, session_scope
from app.models import Campaign, CampaignRecipient, DeliveryJob, DeliveryRun, OutboxMessage
from app.services import outbox
from app.services.campaigns import cancel_campaign
from app.services.dispatch import dispatch_next_due
from app.services.errors import Conflict
from app.timeutil import utcnow
from tests.conftest import add_campaign, add_contact


def count(session, model, *where):
    return session.scalar(select(func.count()).select_from(model).where(*where))


def _due_campaign(audience="vip_customers", minutes_ago=1):
    with session_scope() as s:
        for _ in range(3):
            add_contact(s, segment="vip_customer")
        add_contact(s, segment="vip_customer", subscribed=False)
        add_contact(s, segment="trial_user")
        c = add_campaign(s, audience=audience, status="scheduled", scheduled_at=utcnow() - timedelta(minutes=minutes_ago))
        return c.id


def test_dispatch_snapshots_subscribed_audience_with_one_outbox_row_per_job():
    campaign_id = _due_campaign()
    with session_scope() as s:
        result = dispatch_next_due(s)
    assert result.campaign_id == campaign_id and result.recipient_count == 3

    with session_scope() as s:
        campaign = s.get(Campaign, campaign_id)
        assert campaign.status == "processing" and campaign.recipient_count == 3
        assert count(s, CampaignRecipient, CampaignRecipient.campaign_id == campaign_id) == 3
        assert count(s, DeliveryJob, DeliveryJob.campaign_id == campaign_id) == 3
        assert count(s, OutboxMessage, OutboxMessage.status == "pending") == 3


def test_future_campaign_is_not_dispatched():
    with session_scope() as s:
        add_contact(s)
        c = add_campaign(s, status="scheduled", scheduled_at=utcnow() + timedelta(minutes=2))
        campaign_id = c.id
    with session_scope() as s:
        assert dispatch_next_due(s) is None
    with session_scope() as s:
        assert s.get(Campaign, campaign_id).status == "scheduled"


def test_locked_campaign_is_skipped_by_a_concurrent_dispatcher():
    _due_campaign()
    first = get_sessionmaker()()
    second = get_sessionmaker()()
    try:
        assert dispatch_next_due(first) is not None  # holds the row lock, uncommitted
        assert dispatch_next_due(second) is None  # SKIP LOCKED: no waiting, no double claim
        first.commit()
        second.rollback()
        assert dispatch_next_due(second) is None  # now processing, no longer due
    finally:
        first.close()
        second.close()


def test_overlapping_cron_invocations_dispatch_each_campaign_once():
    with session_scope() as s:
        for _ in range(5):
            add_contact(s, segment="vip_customer")
        ids = [
            add_campaign(s, status="scheduled", scheduled_at=utcnow() - timedelta(minutes=1), name=f"c{i}").id
            for i in range(8)
        ]

    barrier = threading.Barrier(4)

    def cron_like_worker():
        barrier.wait()
        dispatched = 0
        while True:
            with session_scope() as s:
                if dispatch_next_due(s) is None:
                    return dispatched
            dispatched += 1

    with ThreadPoolExecutor(4) as pool:
        total = sum(pool.map(lambda _: cron_like_worker(), range(4)))

    assert total == 8
    with session_scope() as s:
        for campaign_id in ids:
            assert count(s, DeliveryRun, DeliveryRun.campaign_id == campaign_id) == 1
            assert count(s, CampaignRecipient, CampaignRecipient.campaign_id == campaign_id) == 5
        assert count(s, OutboxMessage) == 40


def test_cancel_waits_for_in_flight_dispatch_and_is_rejected():
    campaign_id = _due_campaign()
    dispatcher = get_sessionmaker()()
    assert dispatch_next_due(dispatcher) is not None  # row locked, dispatch in progress

    outcome = {}

    def cancel():
        try:
            with session_scope() as s:
                cancel_campaign(s, campaign_id)
            outcome["result"] = "cancelled"
        except Conflict as exc:
            outcome["result"] = exc.message

    thread = threading.Thread(target=cancel)
    thread.start()
    thread.join(timeout=0.5)
    assert thread.is_alive(), "cancel should block on the dispatcher's row lock"
    dispatcher.commit()
    dispatcher.close()
    thread.join(timeout=5)
    assert "already started sending" in outcome["result"]


def test_cancelled_campaign_is_never_dispatched():
    campaign_id = _due_campaign()
    with session_scope() as s:
        cancel_campaign(s, campaign_id)
    with session_scope() as s:
        assert dispatch_next_due(s) is None
        assert s.get(Campaign, campaign_id).status == "cancelled"
        assert count(s, CampaignRecipient, CampaignRecipient.campaign_id == campaign_id) == 0


def test_empty_audience_completes_with_explanation():
    with session_scope() as s:
        add_contact(s, segment="vip_customer", subscribed=False)
        c = add_campaign(s, status="scheduled", scheduled_at=utcnow() - timedelta(minutes=1))
        campaign_id = c.id
    with session_scope() as s:
        dispatch_next_due(s)
    with session_scope() as s:
        campaign = s.get(Campaign, campaign_id)
        assert campaign.status == "completed"
        assert campaign.status_note == "No eligible recipients"


def test_outbox_leases_prevent_double_publish_and_recover_after_crash():
    _due_campaign()
    with session_scope() as s:
        dispatch_next_due(s)

    with session_scope() as s:
        first = outbox.claim_batch(s, 10)
    with session_scope() as s:
        assert outbox.claim_batch(s, 10) == []  # leased by the first relay

    # Simulate a crash after publishing but before marking: the lease expires.
    with session_scope() as s:
        s.execute(OutboxMessage.__table__.update().values(lease_until=utcnow() - timedelta(seconds=1)))
    with session_scope() as s:
        again = outbox.claim_batch(s, 10)
    assert [m.message_id for m in again] == [m.message_id for m in first]
    with session_scope() as s:
        outbox.mark_published(s, [m.id for m in again])
        assert outbox.pending_count(s) == 0


@pytest.mark.parametrize("action", ["send", "schedule"])
def test_api_rejects_invalid_campaigns_and_reports_fields(action):
    from fastapi.testclient import TestClient

    from app.api.main import app

    client = TestClient(app)
    body = {"name": "", "subject": "", "body": "", "audience": "vip_customers", "action": action}
    if action == "schedule":
        body["scheduled_at"] = (utcnow() - timedelta(minutes=5)).isoformat()
    response = client.post("/api/campaigns", json=body)
    assert response.status_code == 422
    errors = response.json()["errors"]
    assert {"name", "subject", "body", "audience"} <= set(errors)  # audience: no subscribers in test DB
    if action == "schedule":
        assert "future" in errors["scheduled_at"]
    with session_scope() as s:
        assert count(s, Campaign) == 0  # nothing persisted on validation failure
