"""Test that the new high_altitude rule fires correctly."""

from datetime import UTC, datetime

import pytest

from app.alerts.rules import AlertEvaluator
from app.config import settings
from app.readsb.schema import AircraftState


def _mk(hex_code: str, alt: int | None) -> AircraftState:
    return AircraftState(hex=hex_code, alt_baro=alt, updated_at=datetime.now(UTC))


def test_high_altitude_fires_above_threshold():
    ev = AlertEvaluator()
    state = _mk("aaa001", settings.alert_high_altitude_ft + 1000)
    kinds = ev._evaluate(state)  # pylint: disable=protected-access
    assert "high_altitude" in kinds


def test_high_altitude_does_not_fire_at_typical_cruise():
    ev = AlertEvaluator()
    state = _mk("aaa002", 35000)
    kinds = ev._evaluate(state)  # pylint: disable=protected-access
    assert "high_altitude" not in kinds


def test_high_altitude_no_altitude_no_fire():
    ev = AlertEvaluator()
    state = _mk("aaa003", None)
    kinds = ev._evaluate(state)  # pylint: disable=protected-access
    assert "high_altitude" not in kinds
