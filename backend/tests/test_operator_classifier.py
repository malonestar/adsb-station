"""Tests for operator-string military / interesting classification.

Regression: USAF DHC-6 (CONGO65) and similar small-fleet government aircraft
were never flagged as military because readsb's static dbFlags doesn't cover
them. Fix augments the flag with operator-string regex matching.
"""

from __future__ import annotations

import pytest

from app.enrichment.classifier import (
    classify_operator,
    is_known_interesting,
    is_known_military,
    known_interesting_hexes,
    known_military_hexes,
    remember,
)


@pytest.fixture(autouse=True)
def _isolated_sets():
    """Reset module-level sets between tests so they don't leak state."""
    known_military_hexes.clear()
    known_interesting_hexes.clear()
    yield
    known_military_hexes.clear()
    known_interesting_hexes.clear()


# --- regex coverage -------------------------------------------------------


@pytest.mark.parametrize(
    "operator",
    [
        "United States Air Force",
        "United States Army",
        "United States Navy",
        "United States Marine Corps",
        "United States Coast Guard",
        "US Air Force",
        "USAF",
        "USN",
        "USMC",
        "USCG",
        "California Air National Guard",
        "Texas Air National Guard",
        "Department of Defense",
        "DoD",
        "US Customs and Border Protection",
        "CBP",
        "Royal Air Force",
        "Royal Canadian Air Force",
        "Royal Australian Navy",
        "German Air Force",
        "French Navy",
        "Luftwaffe",
    ],
)
def test_classify_military_positive(operator):
    is_mil, is_int = classify_operator(operator)
    assert is_mil is True, f"{operator!r} should be military"
    assert is_int is False, f"{operator!r} should not be interesting"


@pytest.mark.parametrize(
    "operator",
    ["NASA", "National Aeronautics and Space Administration", "FAA",
     "Federal Aviation Administration", "NOAA", "Department of Energy",
     "DOE", "DARPA", "US Forest Service"],
)
def test_classify_interesting_positive(operator):
    is_mil, is_int = classify_operator(operator)
    assert is_mil is False, f"{operator!r} should not be military"
    assert is_int is True, f"{operator!r} should be interesting"


@pytest.mark.parametrize(
    "operator",
    ["United Airlines", "Delta Air Lines", "American Airlines",
     "FedEx", "UPS", "Southwest Airlines", "Alaska Airlines",
     "Spirit Airlines", "Allegiant Air", None, "", "Private owner",
     "John Smith"],
)
def test_classify_civilian_negative(operator):
    is_mil, is_int = classify_operator(operator)
    assert is_mil is False
    assert is_int is False


def test_classify_case_insensitive():
    assert classify_operator("united states air force") == (True, False)
    assert classify_operator("UNITED STATES AIR FORCE") == (True, False)
    assert classify_operator("nasa") == (False, True)


def test_classify_word_boundary_avoids_false_match():
    # "Bus" contains "us" but should not match "us air force"
    assert classify_operator("Greyhound Bus Lines") == (False, False)
    # "USA Today" shouldn't match military
    assert classify_operator("USA Today") == (False, False)


def test_classify_air_force_one_style():
    """Real-world strings the user is likely to see."""
    assert classify_operator("United States Air Force - Air Mobility Command")[0] is True
    assert classify_operator("US Coast Guard")[0] is True
    assert classify_operator("NASA Armstrong Flight Research Center")[1] is True


# --- in-memory cache behavior --------------------------------------------


def test_remember_populates_sets():
    remember("ABC123", military=True, interesting=False)
    assert is_known_military("abc123") is True
    assert is_known_military("ABC123") is True  # case insensitive
    assert is_known_interesting("abc123") is False


def test_remember_both_flags():
    remember("DEF456", military=True, interesting=True)
    assert is_known_military("def456") is True
    assert is_known_interesting("def456") is True


def test_unknown_hex_is_neither():
    assert is_known_military("999999") is False
    assert is_known_interesting("999999") is False
