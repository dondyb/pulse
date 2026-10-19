"""Deterministic delivery simulation. No real email is ever sent.

Outcomes come from stable hashes, so results are repeatable:

* About 3% of email addresses are "bad" (hash of the address): every attempt
  fails with a hard bounce, in every campaign.
* Every other (campaign, contact) pair hashes to a bucket 0-99 that sets how
  many attempts fail before one succeeds. The count is over the recipient's
  attempts across all delivery runs, so recipients that exhaust their automatic
  attempts are delivered by a manual retry.
"""

import hashlib
from dataclasses import dataclass

BAD_ADDRESS_PERCENT = 3

# bucket upper bound (exclusive) -> attempts that fail before success
_PROFILES: list[tuple[int, int]] = [
    (84, 0),  # delivered on the first attempt
    (92, 1),  # one transient failure, then delivered
    (96, 2),  # two transient failures, delivered on the final automatic attempt
    (100, 3),  # exhausts automatic attempts; a manual retry delivers
]

_TRANSIENT_ERRORS = [
    "421 4.7.0 Recipient server busy, try again later (simulated)",
    "Connection to mail server timed out after 10s (simulated)",
    "451 4.3.0 Temporary local problem at recipient server (simulated)",
]
_EXHAUSTING_ERRORS = [
    "452 4.2.2 Recipient mailbox full (simulated)",
    "421 4.4.2 Recipient server rate limit reached (simulated)",
]
_PERMANENT_ERRORS = [
    "550 5.1.1 Recipient address does not exist (simulated)",
    "554 5.7.1 Message rejected by recipient policy (simulated)",
]


@dataclass(frozen=True)
class SimulatedResult:
    success: bool
    error: str | None = None


def _hash(value: str) -> int:
    return int.from_bytes(hashlib.sha256(value.encode()).digest()[:4], "big")


def is_bad_address(email: str) -> bool:
    return _hash(f"pulse:address:{email.strip().lower()}") % 100 < BAD_ADDRESS_PERCENT


def bucket(campaign_id: int, contact_id: int) -> int:
    return _hash(f"pulse:{campaign_id}:{contact_id}") % 100


def failures_before_success(campaign_id: int, contact_id: int, email: str) -> int | None:
    """None means the recipient never succeeds."""
    if is_bad_address(email):
        return None
    b = bucket(campaign_id, contact_id)
    return next(failures for upper, failures in _PROFILES if b < upper)


def simulate(campaign_id: int, contact_id: int, email: str, attempt_number: int) -> SimulatedResult:
    """Outcome of the recipient's `attempt_number`-th attempt overall (1-based)."""
    failures = failures_before_success(campaign_id, contact_id, email)
    if failures is not None and attempt_number > failures:
        return SimulatedResult(success=True)
    b = bucket(campaign_id, contact_id)
    if failures is None:
        pool = _PERMANENT_ERRORS
    elif failures >= 3:
        pool = _EXHAUSTING_ERRORS
    else:
        pool = _TRANSIENT_ERRORS
    return SimulatedResult(success=False, error=pool[(b + attempt_number) % len(pool)])
