"""Circuit breaker tests."""

from __future__ import annotations

import time

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
    b = CircuitBreaker(name="t", failure_threshold=2, reset_after_s=0)
    b.record_failure()
    b.record_failure()
    assert b.is_open
    # Zero reset_after — half_open immediately on next state read
    time.sleep(0.01)
    _ = b.state
    assert b.state == CircuitState.HALF_OPEN


def test_half_open_failure_reopens() -> None:
    b = CircuitBreaker(name="t", failure_threshold=2, reset_after_s=0)
    b.record_failure()
    b.record_failure()
    _ = b.state  # triggers half_open
    b.record_failure()
    assert b.is_open
