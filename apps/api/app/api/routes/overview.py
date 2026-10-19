from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.config import get_settings
from app.db import get_db, get_engine
from app.services import queries
from app.services.dispatch import AUDIENCE_LABELS

router = APIRouter(prefix="/api")

SEGMENT_LABELS = {
    "active_customer": "Active customer",
    "trial_user": "Trial user",
    "vip_customer": "VIP customer",
    "prospect": "Prospect",
}


@router.get("/health", tags=["health"])
def health():
    """Liveness: the process is up and serving requests."""
    return {"status": "ok"}


@router.get("/ready", tags=["health"])
async def ready(request: Request):
    """Readiness: the database is reachable. NATS is reported but optional,
    because outbox rows are published later if it is down."""
    def check_database() -> str:
        try:
            with get_engine().connect() as conn:
                conn.execute(text("SELECT 1"))
            return "ok"
        except Exception:  # noqa: BLE001
            return "unavailable"

    database = await run_in_threadpool(check_database)
    queue = "ok" if await request.app.state.queue.ensure_connected() else "unavailable"
    body = {"status": "ready" if database == "ok" else "not_ready", "database": database, "queue": queue}
    return JSONResponse(body, status_code=200 if database == "ok" else 503)


@router.get("/meta", tags=["meta"])
def meta(session: Session = Depends(get_db)):
    counts = queries.audience_counts(session)
    return {
        "timezone": get_settings().display_timezone,
        "audiences": [{"value": k, "label": v, "eligible": counts[k]} for k, v in AUDIENCE_LABELS.items()],
        "segments": [{"value": k, "label": v} for k, v in SEGMENT_LABELS.items()],
    }


@router.get("/dashboard", tags=["dashboard"])
def dashboard(session: Session = Depends(get_db)):
    return queries.dashboard(session)


@router.get("/activity", tags=["dashboard"])
def activity(limit: int = Query(20, ge=1, le=100), session: Session = Depends(get_db)):
    return {"items": queries.list_activity(session, limit=limit)}


@router.get("/jobs", tags=["jobs"])
def jobs(
    status: str | None = Query(None, pattern="^(queued|processing|retrying|delivered|failed|skipped)$"),
    campaign_id: int | None = None,
    search: str = "",
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    session: Session = Depends(get_db),
):
    return queries.list_jobs(session, status=status, campaign_id=campaign_id, search=search, page=page, page_size=page_size)


@router.get("/jobs/summary", tags=["jobs"])
def jobs_summary(session: Session = Depends(get_db)):
    return queries.job_summary(session)
