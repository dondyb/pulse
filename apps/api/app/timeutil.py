from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.config import get_settings


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def display_tz() -> ZoneInfo:
    return ZoneInfo(get_settings().display_timezone)


def local_day_start(now: datetime | None = None) -> datetime:
    """Start of the current calendar day in the display timezone, as UTC."""
    now = now or utcnow()
    local = now.astimezone(display_tz())
    start = local.replace(hour=0, minute=0, second=0, microsecond=0)
    return start.astimezone(timezone.utc)


def floor_minute(value: datetime) -> datetime:
    return value.replace(second=0, microsecond=0)


def days_ago(days: float, now: datetime | None = None) -> datetime:
    return (now or utcnow()) - timedelta(days=days)
