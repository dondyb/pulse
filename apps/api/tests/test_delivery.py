"""Worker processing: idempotency, leases, automatic retries, manual retries, consent."""

from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app.db import session_scope
from app.models import Campaign, CampaignRecipient, DeliveryAttempt, DeliveryJob, DeliveryRun, OutboxMessage
from app.services.campaigns import retry_failed
from app.services.delivery import Claim, Decision, begin_attempt, complete_attempt
from app.services.dispatch import dispatch_campaign
from app.services.errors import Conflict
from app.services.simulation import simulate
from app.timeutil import utcnow
from tests.conftest import add_campaign, add_contact_with_profile


def attempt(job_id: int, worker: str = "w1", now=None):
    """One worker pass over a message: claim, simulate, persist."""
    with session_scope() as s:
        claim = begin_attempt(s, job_id, worker, now)
    if isinstance(claim, Decision):
        return claim
    result = simulate(claim.campaign_id, claim.contact_id, claim.email, claim.overall_attempt)
    with session_scope() as s:
        return complete_attempt(s, claim, result, worker, now)


def setup_campaign(*profiles):
    """Dispatch a campaign whose recipients have the given failure profiles. Returns (campaign_id, [job_ids])."""
    with session_scope() as s:
        campaign = add_campaign(s)
        for failures in profiles:
            add_contact_with_profile(s, campaign.id, failures)
        dispatch_campaign(s, campaign)
        campaign_id = campaign.id
    with session_scope() as s:
        jobs = s.scalars(
            select(DeliveryJob.id).where(DeliveryJob.campaign_id == campaign_id).order_by(DeliveryJob.id)
        ).all()
    return campaign_id, list(jobs)


def attempts_for(session, job_id):
    return session.scalar(select(func.count()).select_from(DeliveryAttempt).where(DeliveryAttempt.job_id == job_id))


def test_redelivered_message_does_not_duplicate_a_successful_delivery():
    campaign_id, [job_id] = setup_campaign(0)
    assert attempt(job_id).reason == "delivered"

    duplicate = attempt(job_id)
    assert duplicate.action == "ack" and "duplicate" in duplicate.reason
    with session_scope() as s:
        assert attempts_for(s, job_id) == 1
        recipient = s.scalars(select(CampaignRecipient).where(CampaignRecipient.campaign_id == campaign_id)).one()
        assert recipient.status == "delivered" and recipient.attempt_count == 1
        assert s.get(Campaign, campaign_id).status == "completed"


def test_concurrent_duplicate_message_is_deferred_while_job_is_leased():
    _, [job_id] = setup_campaign(0)
    with session_scope() as s:
        claim = begin_attempt(s, job_id, "w1")
    assert isinstance(claim, Claim)

    second = attempt(job_id, worker="w2")  # same job, another message copy
    assert second.action == "nak" and "leased" in second.reason
    with session_scope() as s:
        assert attempts_for(s, job_id) == 1


def test_expired_lease_is_taken_over_without_a_second_attempt_record():
    _, [job_id] = setup_campaign(0)
    with session_scope() as s:
        stale = begin_attempt(s, job_id, "crashed-worker")
    later = utcnow() + timedelta(minutes=5)

    assert attempt(job_id, worker="w2", now=later).reason == "delivered"
    with session_scope() as s:
        assert attempts_for(s, job_id) == 1  # same execution, same record
    # The original worker wakes up and tries to save its result: discarded.
    with session_scope() as s:
        late = complete_attempt(s, stale, simulate(stale.campaign_id, stale.contact_id, stale.email, 1), "crashed-worker")
    assert late.reason == "stale attempt result discarded"


def test_transient_failure_is_retried_after_a_persisted_delay():
    campaign_id, [job_id] = setup_campaign(1)
    first = attempt(job_id)
    assert first.action == "nak" and first.delay == 5  # NAK with delay, no sleeping worker

    with session_scope() as s:
        job = s.get(DeliveryJob, job_id)
        assert job.status == "retrying" and job.next_attempt_at is not None
        due = job.next_attempt_at

    early = attempt(job_id)  # message redelivered before the retry is due
    assert early.action == "nak" and early.reason == "retry not due yet"

    assert attempt(job_id, now=due + timedelta(seconds=1)).reason == "delivered"
    with session_scope() as s:
        assert attempts_for(s, job_id) == 2
        assert s.get(Campaign, campaign_id).status == "completed"


def test_exhausted_attempts_fail_and_manual_retry_preserves_history():
    campaign_id, [job_id] = setup_campaign(3)
    now = utcnow()
    for _ in range(3):
        decision = attempt(job_id, now=now)
        now += timedelta(seconds=decision.delay + 1)
    assert decision.reason == "failed permanently"

    with session_scope() as s:
        campaign = s.get(Campaign, campaign_id)
        assert campaign.status == "completed" and "1 failed" in campaign.status_note

    with session_scope() as s:
        retry_failed(s, campaign_id)
    with pytest.raises(Conflict):  # repeated click while the retry run is active
        with session_scope() as s:
            retry_failed(s, campaign_id)

    with session_scope() as s:
        runs = s.scalars(select(DeliveryRun).where(DeliveryRun.campaign_id == campaign_id).order_by(DeliveryRun.run_number)).all()
        assert [(r.kind, r.status) for r in runs] == [("initial", "finished"), ("manual_retry", "active")]
        new_job = s.scalars(select(DeliveryJob.id).where(DeliveryJob.run_id == runs[1].id)).one()
        assert s.scalar(select(func.count()).select_from(OutboxMessage).where(OutboxMessage.job_id == new_job)) == 1

    assert attempt(new_job, now=now).reason == "delivered"  # 4th attempt overall succeeds
    with session_scope() as s:
        recipient = s.scalars(select(CampaignRecipient).where(CampaignRecipient.campaign_id == campaign_id)).one()
        assert recipient.status == "delivered" and recipient.attempt_count == 4
        history = s.scalars(
            select(DeliveryAttempt.outcome).where(DeliveryAttempt.recipient_id == recipient.id).order_by(DeliveryAttempt.id)
        ).all()
        assert history == ["failure", "failure", "failure", "success"]
        assert s.get(Campaign, campaign_id).status == "completed"


def test_retry_failed_requires_finished_campaign_with_failures():
    campaign_id, [job_id] = setup_campaign(0)
    with pytest.raises(Conflict):  # still processing
        with session_scope() as s:
            retry_failed(s, campaign_id)
    attempt(job_id)
    with pytest.raises(Conflict, match="no failed deliveries"):
        with session_scope() as s:
            retry_failed(s, campaign_id)


def test_recipient_who_unsubscribes_after_dispatch_is_skipped():
    campaign_id, jobs = setup_campaign(0, 0)
    with session_scope() as s:
        recipient = s.get(DeliveryJob, jobs[0]).recipient
        recipient.contact.subscribed = False

    skipped = attempt(jobs[0])
    assert skipped.reason == "recipient skipped"
    attempt(jobs[1])
    with session_scope() as s:
        statuses = sorted(s.scalars(select(CampaignRecipient.status).where(CampaignRecipient.campaign_id == campaign_id)))
        assert statuses == ["delivered", "skipped"]
        campaign = s.get(Campaign, campaign_id)
        assert campaign.status == "completed" and "1 skipped" in campaign.status_note
        assert attempts_for(s, jobs[0]) == 0


def test_last_two_jobs_finishing_concurrently_complete_the_campaign_once():
    campaign_id, jobs = setup_campaign(0, 0)
    with session_scope() as s:
        claims = [begin_attempt(s, job_id, "w1") for job_id in jobs]

    from concurrent.futures import ThreadPoolExecutor

    def finish(claim):
        with session_scope() as s:
            return complete_attempt(s, claim, simulate(claim.campaign_id, claim.contact_id, claim.email, 1), "w1")

    with ThreadPoolExecutor(2) as pool:
        list(pool.map(finish, claims))
    with session_scope() as s:
        assert s.get(Campaign, campaign_id).status == "completed"
        from app.models import ActivityEvent

        completions = s.scalar(
            select(func.count())
            .select_from(ActivityEvent)
            .where(ActivityEvent.campaign_id == campaign_id, ActivityEvent.kind == "campaign.completed")
        )
        assert completions == 1
