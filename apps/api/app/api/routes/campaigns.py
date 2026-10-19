from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.api.schemas import CampaignIn
from app.db import get_db, session_scope
from app.models import Campaign, CampaignRecipient
from app.services import campaigns as service
from app.services import queries
from app.services.errors import NotFound

router = APIRouter(prefix="/api/campaigns", tags=["campaigns"])

STATUS_FILTER = "^(draft|scheduled|processing|completed|completed_with_failures|cancelled)$"


def _get(session: Session, campaign_id: int) -> Campaign:
    campaign = session.get(Campaign, campaign_id)
    if campaign is None:
        raise NotFound("Campaign not found.")
    return campaign


def _to_input(body: CampaignIn) -> service.CampaignInput:
    return service.CampaignInput(**body.model_dump())


def _detail(campaign_id: int) -> dict:
    with session_scope() as session:
        return queries.campaign_detail(session, _get(session, campaign_id))


async def _publish_and_respond(request: Request, campaign_id: int, should_publish: bool) -> dict:
    queued = None
    if should_publish:
        queued = await request.app.state.queue.publish_campaign(campaign_id)
    detail = await run_in_threadpool(_detail, campaign_id)
    detail["queue_published"] = queued
    return detail


@router.get("")
def list_campaigns(
    search: str = "",
    status: str | None = Query(None, pattern=STATUS_FILTER),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    session: Session = Depends(get_db),
):
    return queries.list_campaigns(session, search=search, status=status, page=page, page_size=page_size)


@router.post("", status_code=201)
async def create_campaign(body: CampaignIn, request: Request):
    def work():
        with session_scope() as session:
            campaign = service.create_campaign(session, _to_input(body))
            return campaign.id, campaign.status == "processing"

    campaign_id, dispatched = await run_in_threadpool(work)
    return await _publish_and_respond(request, campaign_id, dispatched)


@router.get("/{campaign_id}")
def get_campaign(campaign_id: int, session: Session = Depends(get_db)):
    return queries.campaign_detail(session, _get(session, campaign_id))


@router.put("/{campaign_id}")
async def update_campaign(campaign_id: int, body: CampaignIn, request: Request):
    def work():
        with session_scope() as session:
            campaign = service.update_campaign(session, campaign_id, _to_input(body))
            return campaign.status == "processing"

    dispatched = await run_in_threadpool(work)
    return await _publish_and_respond(request, campaign_id, dispatched)


@router.post("/{campaign_id}/duplicate", status_code=201)
def duplicate_campaign(campaign_id: int, session: Session = Depends(get_db)):
    copy = service.duplicate_campaign(session, campaign_id)
    session.commit()
    return queries.campaign_detail(session, copy)


@router.post("/{campaign_id}/cancel")
def cancel_campaign(campaign_id: int, session: Session = Depends(get_db)):
    campaign = service.cancel_campaign(session, campaign_id)
    session.commit()
    return queries.campaign_detail(session, campaign)


@router.post("/{campaign_id}/retry-failed")
async def retry_failed(campaign_id: int, request: Request):
    def work():
        with session_scope() as session:
            service.retry_failed(session, campaign_id)

    await run_in_threadpool(work)
    return await _publish_and_respond(request, campaign_id, True)


@router.get("/{campaign_id}/recipients")
def list_recipients(
    campaign_id: int,
    status: str | None = Query(None, pattern="^(pending|delivered|failed|skipped)$"),
    search: str = "",
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    session: Session = Depends(get_db),
):
    _get(session, campaign_id)
    return queries.list_recipients(session, campaign_id, status=status, search=search, page=page, page_size=page_size)


@router.get("/{campaign_id}/recipients/{recipient_id}/attempts")
def recipient_attempts(campaign_id: int, recipient_id: int, session: Session = Depends(get_db)):
    recipient = session.get(CampaignRecipient, recipient_id)
    if recipient is None or recipient.campaign_id != campaign_id:
        raise NotFound("Recipient not found.")
    return {"items": queries.recipient_attempts(session, campaign_id, recipient_id)}


@router.get("/{campaign_id}/activity")
def campaign_activity(
    campaign_id: int,
    limit: int = Query(40, ge=1, le=200),
    milestones_only: bool = False,
    session: Session = Depends(get_db),
):
    _get(session, campaign_id)
    return {"items": queries.list_activity(session, campaign_id=campaign_id, limit=limit, milestones_only=milestones_only)}
