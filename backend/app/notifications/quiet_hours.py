"""Quiet-hours logic. Email deliveries skip when the station-local time
falls inside the configured window. Handles windows crossing midnight."""

from __future__ import annotations

from datetime import time


def _parse(value: str | None) -> time | None:
    if not value:
        return None
    try:
        hh, mm = value.split(":")
        return time(int(hh), int(mm))
    except (ValueError, TypeError):
        return None


def is_quiet(now: time, start: str | None, end: str | None) -> bool:
    """Return True if `now` is within the [start, end) quiet window.

    Both start and end must be set; otherwise the window is disabled.
    Handles overnight windows where start > end (e.g., 22:00 → 07:00).
    """
    t_start = _parse(start)
    t_end = _parse(end)
    if t_start is None or t_end is None:
        return False

    if t_start <= t_end:
        # Straight window: quiet when start <= now < end
        return t_start <= now < t_end
    # Overnight window: quiet when now >= start OR now < end
    return now >= t_start or now < t_end
