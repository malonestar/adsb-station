"""Rolling live-stats aggregator. Publishes stats.tick every poll."""

from __future__ import annotations

from collections import deque
from datetime import UTC, datetime
from typing import Any

from app.events.bus import bus
from app.logging import get_logger
from app.readsb.schema import AircraftDelta, AircraftState

log = get_logger(__name__)

# Signal-strength histogram buckets (dBFS) — from -40 (weakest) to 0 (strongest)
_RSSI_BUCKETS = list(range(-40, 1, 2))  # -40, -38, ..., 0


class LiveStats:
    def __init__(self) -> None:
        self._prev_msg_total: int | None = None
        self._msgs_per_sec_window: deque[tuple[datetime, int]] = deque(maxlen=60)
        self._max_range_today: float = 0.0
        self._max_range_today_date: str = ""

    async def on_delta(
        self,
        delta: AircraftDelta,
        states: list[AircraftState],
        now: datetime,
    ) -> None:
        # Aggregate message count across all live aircraft (readsb reports per-aircraft totals)
        msg_total = sum(s.messages for s in states)
        msgs_this_tick: int = 0
        if self._prev_msg_total is not None:
            # Handle reset if poller/container restarts
            msgs_this_tick = max(0, msg_total - self._prev_msg_total)
        self._prev_msg_total = msg_total
        self._msgs_per_sec_window.append((now, msgs_this_tick))

        # Max-range-today
        today = now.date().isoformat()
        if today != self._max_range_today_date:
            self._max_range_today = 0.0
            self._max_range_today_date = today
        for s in states:
            if s.distance_nm is not None and s.distance_nm > self._max_range_today:
                self._max_range_today = s.distance_nm

        tick = self.snapshot(states, now)
        await bus.publish("stats.tick", tick)

    def snapshot(self, states: list[AircraftState], now: datetime) -> dict[str, Any]:
        # Messages per second — average over the 60s window
        cutoff = now.timestamp() - 60
        recent = [v for (ts, v) in self._msgs_per_sec_window if ts.timestamp() >= cutoff]
        msgs_per_sec = (sum(recent) / max(1, len(recent))) if recent else 0.0

        with_pos = [s for s in states if s.lat is not None and s.lon is not None]

        return {
            "ts": now.isoformat(),
            "messages_per_sec": round(msgs_per_sec, 1),
            "aircraft_total": len(states),
            "aircraft_with_position": len(with_pos),
            "max_range_nm_today": round(self._max_range_today, 1),
            "signal_histogram": _histogram([s.rssi for s in states if s.rssi is not None]),
        }


def _histogram(values: list[float]) -> list[dict[str, float | int]]:
    """Bin RSSI values into buckets. Returns [{bucket, count}, ...]"""
    buckets = {b: 0 for b in _RSSI_BUCKETS}
    for v in values:
        # Round down to nearest 2 dBFS
        b = max(-40, min(0, int(v // 2) * 2))
        if b in buckets:
            buckets[b] += 1
    return [{"bucket": b, "count": c} for b, c in sorted(buckets.items())]


live_stats = LiveStats()
