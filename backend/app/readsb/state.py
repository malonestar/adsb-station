"""In-memory aircraft registry — computes deltas between snapshots."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.readsb.schema import AircraftDelta, AircraftState

# Drop aircraft from the live set after this long without updates
_STALE_AFTER = timedelta(seconds=60)


class AircraftRegistry:
    def __init__(self) -> None:
        self._by_hex: dict[str, AircraftState] = {}

    def snapshot(self) -> list[AircraftState]:
        return list(self._by_hex.values())

    def get(self, hex_code: str) -> AircraftState | None:
        return self._by_hex.get(hex_code)

    def apply(self, states: list[AircraftState]) -> AircraftDelta:
        """Diff new states against the current registry, return the change set."""
        now = datetime.now(UTC)
        incoming = {s.hex: s for s in states}

        added: list[AircraftState] = []
        updated: list[AircraftState] = []
        removed: list[str] = []

        for hex_code, state in incoming.items():
            if hex_code not in self._by_hex:
                added.append(state)
            elif self._changed(self._by_hex[hex_code], state):
                updated.append(state)
            self._by_hex[hex_code] = state

        # Age out aircraft that haven't reappeared in the snapshot for too long.
        for hex_code, prev in list(self._by_hex.items()):
            if hex_code in incoming:
                continue
            if now - prev.updated_at > _STALE_AFTER:
                removed.append(hex_code)
                del self._by_hex[hex_code]

        return AircraftDelta(added=added, updated=updated, removed=removed)

    @staticmethod
    def _changed(prev: AircraftState, curr: AircraftState) -> bool:
        """Only emit updates for fields the UI cares about."""
        return (
            prev.lat != curr.lat
            or prev.lon != curr.lon
            or prev.alt_baro != curr.alt_baro
            or prev.gs != curr.gs
            or prev.track != curr.track
            or prev.baro_rate != curr.baro_rate
            or prev.squawk != curr.squawk
            or prev.emergency != curr.emergency
            or prev.flight != curr.flight
            or prev.messages != curr.messages
        )
