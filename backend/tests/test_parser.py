"""Parser unit tests — pure functions, no IO."""

from __future__ import annotations

from datetime import UTC, datetime

from app.readsb.parser import bearing_deg, haversine_nm, parse_aircraft, parse_snapshot


def test_haversine_known_distance() -> None:
    # Aurora CO (39.7, -104.8) to DIA (39.862, -104.673)
    d = haversine_nm(39.7, -104.8, 39.862, -104.673)
    assert 11.0 < d < 13.0


def test_bearing_cardinal() -> None:
    # Due east
    b = bearing_deg(39.7, -104.8, 39.7, -104.0)
    assert 88 < b < 92


def test_parse_aircraft_minimal() -> None:
    raw = {
        "hex": "a1b2c3",
        "flight": "UAL123  ",
        "lat": 39.862,
        "lon": -104.673,
        "alt_baro": 12000,
        "gs": 280.5,
        "track": 270.0,
        "squawk": "1234",
        "messages": 42,
        "seen": 0.5,
        "rssi": -22.4,
        "dbFlags": 0,
    }
    ac = parse_aircraft(raw, now=datetime(2026, 4, 19, tzinfo=UTC))
    assert ac.hex == "a1b2c3"
    assert ac.flight == "UAL123"
    assert ac.alt_baro == 12000
    assert ac.distance_nm is not None and 11.0 < ac.distance_nm < 13.0
    assert ac.bearing_deg is not None and 0 <= ac.bearing_deg < 360
    assert ac.is_military is False
    assert ac.is_emergency is False


def test_parse_aircraft_military_flag() -> None:
    raw = {"hex": "aeff01", "dbFlags": 1, "messages": 1, "seen": 0}
    ac = parse_aircraft(raw)
    assert ac.is_military is True


def test_parse_aircraft_emergency_squawk() -> None:
    raw = {"hex": "abcd12", "squawk": "7700", "messages": 1, "seen": 0}
    ac = parse_aircraft(raw)
    assert ac.is_emergency is True


def test_parse_snapshot_skips_malformed() -> None:
    payload = {
        "aircraft": [
            {"hex": "a1b2c3", "messages": 1, "seen": 0},
            {"no_hex": True},  # malformed
            None,  # malformed
        ]
    }
    result = parse_snapshot(payload)
    assert len(result) == 1
    assert result[0].hex == "a1b2c3"
