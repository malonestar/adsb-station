"""Tests for the email-only quiet-hours window."""

from datetime import time

import pytest

from app.notifications.quiet_hours import is_quiet


def test_disabled_when_no_window():
    assert is_quiet(time(3, 0), None, None) is False
    assert is_quiet(time(3, 0), "22:00", None) is False
    assert is_quiet(time(3, 0), None, "07:00") is False


def test_inside_straight_window_is_quiet():
    # Window 13:00 - 15:00
    assert is_quiet(time(14, 0), "13:00", "15:00") is True


def test_outside_straight_window_is_not_quiet():
    assert is_quiet(time(16, 0), "13:00", "15:00") is False


def test_inside_overnight_window_is_quiet():
    # Window 22:00 - 07:00
    assert is_quiet(time(3, 0), "22:00", "07:00") is True
    assert is_quiet(time(23, 30), "22:00", "07:00") is True
    assert is_quiet(time(6, 59), "22:00", "07:00") is True


def test_outside_overnight_window_is_not_quiet():
    assert is_quiet(time(7, 0), "22:00", "07:00") is False  # exactly at end = not quiet
    assert is_quiet(time(12, 0), "22:00", "07:00") is False
    assert is_quiet(time(21, 59), "22:00", "07:00") is False


def test_boundary_start_is_quiet():
    assert is_quiet(time(22, 0), "22:00", "07:00") is True


def test_malformed_input_returns_false():
    assert is_quiet(time(3, 0), "not-a-time", "07:00") is False
