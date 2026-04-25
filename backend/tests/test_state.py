"""AircraftRegistry delta-computation tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.readsb.schema import AircraftState
from app.readsb.state import AircraftRegistry


def _state(hex_code: str, *, lat: float = 0.0, lon: float = 0.0, messages: int = 1) -> AircraftState:
    return AircraftState(
        hex=hex_code,
        lat=lat,
        lon=lon,
        messages=messages,
        seen=0.0,
        db_flags=0,
        updated_at=datetime.now(UTC),
    )


def test_first_snapshot_all_added() -> None:
    r = AircraftRegistry()
    delta = r.apply([_state("a"), _state("b")])
    assert len(delta.added) == 2
    assert not delta.updated
    assert not delta.removed


def test_second_snapshot_detects_update() -> None:
    r = AircraftRegistry()
    r.apply([_state("a", messages=1)])
    delta = r.apply([_state("a", messages=2)])
    assert not delta.added
    assert len(delta.updated) == 1
    assert not delta.removed


def test_no_change_no_update() -> None:
    r = AircraftRegistry()
    r.apply([_state("a", messages=1)])
    delta = r.apply([_state("a", messages=1)])
    assert not delta.added
    assert not delta.updated


def test_stale_aircraft_removed() -> None:
    r = AircraftRegistry()
    stale = _state("a")
    stale.updated_at = datetime.now(UTC) - timedelta(seconds=120)
    r._by_hex["a"] = stale
    delta = r.apply([])
    assert delta.removed == ["a"]
