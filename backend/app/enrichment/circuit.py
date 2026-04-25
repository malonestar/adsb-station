"""Async circuit breaker — keeps flaky upstreams from stalling the backend."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from enum import Enum

from app.config import settings
from app.logging import get_logger

log = get_logger(__name__)


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """Three-state breaker. Single-threaded — safe inside one event loop."""

    def __init__(
        self,
        name: str,
        failure_threshold: int | None = None,
        reset_after_s: int | None = None,
    ) -> None:
        self.name = name
        # `or` would treat 0 as "no value" (it's falsy) and silently swap in the
        # settings default — making it impossible to pass a real zero. Use an
        # explicit None check so callers can opt in to immediate-transition
        # breakers (mainly tests).
        self.failure_threshold = (
            failure_threshold if failure_threshold is not None else settings.cb_failure_threshold
        )
        self.reset_after = timedelta(
            seconds=reset_after_s if reset_after_s is not None else settings.cb_reset_after_s
        )
        self._state = CircuitState.CLOSED
        self._fail_count = 0
        self._opened_at: datetime | None = None

    @property
    def state(self) -> CircuitState:
        if self._state == CircuitState.OPEN and self._opened_at is not None:
            if datetime.now(UTC) - self._opened_at >= self.reset_after:
                self._state = CircuitState.HALF_OPEN
                log.info("circuit_half_open", name=self.name)
        return self._state

    @property
    def is_open(self) -> bool:
        return self.state == CircuitState.OPEN

    def record_success(self) -> None:
        if self._state != CircuitState.CLOSED:
            log.info("circuit_closed", name=self.name)
        self._state = CircuitState.CLOSED
        self._fail_count = 0
        self._opened_at = None

    def record_failure(self) -> None:
        self._fail_count += 1
        if self._state == CircuitState.HALF_OPEN:
            self._trip()
            return
        if self._fail_count >= self.failure_threshold:
            self._trip()

    def _trip(self) -> None:
        self._state = CircuitState.OPEN
        self._opened_at = datetime.now(UTC)
        log.warning("circuit_open", name=self.name, fails=self._fail_count)
