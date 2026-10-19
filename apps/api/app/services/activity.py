from datetime import datetime

from sqlalchemy.orm import Session

from app.models import ActivityEvent


def record(
    session: Session,
    kind: str,
    message: str,
    *,
    campaign_id: int | None = None,
    recipient_id: int | None = None,
    level: str = "info",
    at: datetime | None = None,
) -> ActivityEvent:
    event = ActivityEvent(
        kind=kind,
        message=message[:300],
        campaign_id=campaign_id,
        recipient_id=recipient_id,
        level=level,
    )
    if at is not None:
        event.created_at = at
    session.add(event)
    return event
