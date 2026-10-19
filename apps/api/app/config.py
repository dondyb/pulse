from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Hosting platforms (e.g. NEO App database bindings) usually inject a plain
# postgres:// or postgresql:// URL; SQLAlchemy needs the psycopg 3 driver named.
_DRIVERLESS_SCHEMES = ("postgres://", "postgresql://")


def normalize_database_url(url: str) -> str:
    url = url.strip()
    for scheme in _DRIVERLESS_SCHEMES:
        if url.startswith(scheme):
            return "postgresql+psycopg://" + url[len(scheme):]
    return url


class Settings(BaseSettings):
    """Runtime configuration, read from environment variables."""

    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    database_url: str = "postgresql+psycopg://pulse:pulse@localhost:5432/pulse"
    nats_url: str = "nats://localhost:4222"
    # Optional credentials, used when they are not already embedded in NATS_URL.
    nats_user: str | None = None
    nats_password: str | None = None
    nats_stream: str = "PULSE_DELIVERIES"
    nats_subject: str = "pulse.deliveries.email"
    nats_consumer: str = "delivery-worker"
    nats_connect_timeout_seconds: float = 3.0

    port: int = 8000  # API listen port (PORT), used by `python -m app.cli serve`
    log_level: str = "INFO"
    display_timezone: str = "Asia/Jakarta"
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    # Worker / delivery simulation
    worker_concurrency: int = 2
    sim_delay_min_ms: int = 600
    sim_delay_max_ms: int = 1000
    delivery_max_attempts: int = 3
    retry_delays_seconds: str = "5,20"
    job_lease_seconds: int = 30
    worker_heartbeat_seconds: int = 5

    # Cron dispatch
    cron_campaign_batch: int = 20
    cron_outbox_batch: int = 500
    cron_max_seconds: int = 45
    outbox_lease_seconds: int = 30

    # Seeding
    demo_schedule_offset_minutes: int = 5

    @field_validator("database_url")
    @classmethod
    def _normalize_database_url(cls, value: str) -> str:
        return normalize_database_url(value)

    @property
    def retry_delays(self) -> list[int]:
        return [int(part) for part in self.retry_delays_seconds.split(",") if part.strip()] or [5]

    def retry_delay_for(self, failed_attempt: int) -> int:
        """Delay before the attempt following `failed_attempt` (1-based)."""
        delays = self.retry_delays
        return delays[min(failed_attempt - 1, len(delays) - 1)]


@lru_cache
def get_settings() -> Settings:
    return Settings()
