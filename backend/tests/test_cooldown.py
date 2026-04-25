"""Tests for the per-hex-per-kind cooldown tracker."""

from datetime import UTC, datetime, timedelta

import pytest

from app.notifications.cooldown import CooldownTracker


def test_first_event_is_allowed():
    ct = CooldownTracker(ttl=timedelta(hours=6))
    now = datetime(2026, 4, 21, 12, 0, tzinfo=UTC)
    assert ct.allow("ae0123", "military", now) is True


def test_second_event_within_ttl_is_blocked():
    ct = CooldownTracker(ttl=timedelta(hours=6))
    t0 = datetime(2026, 4, 21, 12, 0, tzinfo=UTC)
    ct.allow("ae0123", "military", t0)
    t1 = t0 + timedelta(hours=3)
    assert ct.allow("ae0123", "military", t1) is False


def test_event_after_ttl_is_allowed_again():
    ct = CooldownTracker(ttl=timedelta(hours=6))
    t0 = datetime(2026, 4, 21, 12, 0, tzinfo=UTC)
    ct.allow("ae0123", "military", t0)
    t1 = t0 + timedelta(hours=7)
    assert ct.allow("ae0123", "military", t1) is True


def test_different_kind_is_independent():
    """A plane cooling down on 'military' should still notify on 'emergency'."""
    ct = CooldownTracker(ttl=timedelta(hours=6))
    t0 = datetime(2026, 4, 21, 12, 0, tzinfo=UTC)
    ct.allow("ae0123", "military", t0)
    assert ct.allow("ae0123", "emergency", t0) is True


def test_different_hex_is_independent():
    ct = CooldownTracker(ttl=timedelta(hours=6))
    t0 = datetime(2026, 4, 21, 12, 0, tzinfo=UTC)
    ct.allow("ae0123", "military", t0)
    assert ct.allow("ae0456", "military", t0) is True


def test_emergency_bypasses_cooldown_via_bypass_flag():
    """Dispatcher passes bypass=True for emergency alerts."""
    ct = CooldownTracker(ttl=timedelta(hours=6))
    t0 = datetime(2026, 4, 21, 12, 0, tzinfo=UTC)
    ct.allow("ae0123", "emergency", t0)
    t1 = t0 + timedelta(minutes=5)
    assert ct.allow("ae0123", "emergency", t1, bypass=True) is True
