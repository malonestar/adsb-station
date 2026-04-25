"""Circuit breaker tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.enrichment.circuit import CircuitBreaker, CircuitState


def test_trips_after_threshold() -> None:
    b = CircuitBreaker(name="t", failure_threshold=3, reset_after_s=1)
    for _ in range(3):
        b.record_failure()
    assert b.is_open
    assert b.state == CircuitState.OPEN


def test_success_resets() -> None:
    b = CircuitBreaker(name="t", failure_threshold=3, reset_after_s=1)
    b.record_failure()
    b.record_failure()
    b.record_success()
    assert not b.is_open


def test_half_open_after_reset_window() -> None:
    """After reset_after elapses, the next state read transitions to HALF_OPEN."""
    b = CircuitBreaker(name="t", failure_threshold=2, reset_after_s=1)
    b.record_failure()
    b.record_failure()
    assert b.is_open
    # Backdate the trip so the reset window has clearly elapsed — avoids a
    # wall-clock race in tests without needing time.sleep / freezegun.
    b._opened_at = datetime.now(UTC) - timedelta(seconds=2)
    assert b.state == CircuitState.HALF_OPEN


def test_half_open_failure_reopens() -> None:
    """A failure while HALF_OPEN must trip back to OPEN immediately."""
    b = CircuitBreaker(name="t", failure_threshold=2, reset_after_s=1)
    b.record_failure()
    b.record_failure()
    b._opened_at = datetime.now(UTC) - timedelta(seconds=2)
    _ = b.state  # triggers half_open
    assert b.state == CircuitState.HALF_OPEN
    b.record_failure()
    assert b.is_open
