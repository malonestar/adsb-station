"""Tests for the polar antenna-coverage metric extension."""

import os
import sys
from unittest.mock import patch

import pytest
from prometheus_client import CollectorRegistry, Gauge

# Make `import exporter` work without installing the package.
_HERE = os.path.dirname(os.path.abspath(__file__))
_PARENT = os.path.dirname(_HERE)
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)

import exporter as exporter_mod  # noqa: E402
from exporter import compute_polar_bins, haversine_nm  # noqa: E402


# --- haversine_nm ---


def test_haversine_zero_distance():
    assert haversine_nm(40.0, -105.0, 40.0, -105.0) == pytest.approx(0.0, abs=1e-9)


def test_haversine_one_degree_latitude():
    # 1 degree of latitude ~ 60 nm
    assert haversine_nm(40.0, -105.0, 41.0, -105.0) == pytest.approx(60.0, abs=0.5)


def test_haversine_one_degree_longitude_at_40n():
    # 1 degree of longitude at 40N ~ 46 nm (cos(40) * 60)
    assert haversine_nm(40.0, -105.0, 40.0, -104.0) == pytest.approx(46.0, abs=1.0)


def test_haversine_is_symmetric():
    a = haversine_nm(40.0, -105.0, 41.5, -104.3)
    b = haversine_nm(41.5, -104.3, 40.0, -105.0)
    assert a == pytest.approx(b, abs=1e-9)


# --- compute_polar_bins ---


def test_compute_polar_bins_returns_36_values():
    # All 360 points are exactly at the station -> every bin max == 0.
    pts = [[40.0, -105.0, 10000] for _ in range(360)]
    bins = compute_polar_bins(pts, 40.0, -105.0)
    assert len(bins) == 36
    assert all(b == pytest.approx(0.0, abs=1e-9) for b in bins)


def test_compute_polar_bins_takes_max_per_bin():
    # Baseline: 360 points at 0.5 deg north of station (~30 nm).
    baseline_lat = 40.5
    pts = [[baseline_lat, -105.0, 10000] for _ in range(360)]
    # Bump indices 0..9 (bin 0) up to 2 deg north (~120 nm).
    for i in range(10):
        pts[i] = [42.0, -105.0, 10000]

    bins = compute_polar_bins(pts, 40.0, -105.0)
    assert len(bins) == 36
    assert bins[0] == pytest.approx(120.0, abs=1.5)
    for i in range(1, 36):
        assert bins[i] == pytest.approx(30.0, abs=1.0)


def test_compute_polar_bins_rejects_wrong_length():
    with pytest.raises(ValueError):
        compute_polar_bins([[40.0, -105.0, 0]] * 100, 40.0, -105.0)


# --- update_polar ---


def _fake_outline(points):
    return {"actualRange": {"last24h": {"points": points}}}


@pytest.fixture
def fresh_polar_gauge(monkeypatch):
    """Swap exporter_mod.polar_range_nm for a Gauge on a private registry.

    This gives each test a clean slate with zero cross-test leakage, and
    avoids reaching into prometheus-client's private `_metrics` dict.
    """
    registry = CollectorRegistry()
    gauge = Gauge(
        "adsb_polar_range_nm",
        "Max observed range per 10-degree compass bearing bin (nautical miles), last 24h",
        labelnames=["bearing"],
        registry=registry,
    )
    monkeypatch.setattr(exporter_mod, "polar_range_nm", gauge)
    return gauge


def _polar_samples(gauge):
    """Return [(bearing_label, value), ...] via the public collect() API."""
    return [
        (sample.labels["bearing"], sample.value)
        for metric in gauge.collect()
        for sample in metric.samples
    ]


def test_update_polar_sets_36_series_on_valid_outline(fresh_polar_gauge):
    pts = [[40.5, -105.0, 10000] for _ in range(360)]

    def fake_fetch(path):
        assert path == "/data/outline.json"
        return _fake_outline(pts)

    with patch.object(exporter_mod, "fetch_json", side_effect=fake_fetch):
        exporter_mod.update_polar(40.0, -105.0)

    samples = _polar_samples(fresh_polar_gauge)
    assert len(samples) == 36
    for _label, value in samples:
        assert value == pytest.approx(30.0, abs=1.0)


def test_update_polar_survives_missing_outline(fresh_polar_gauge):
    def fake_fetch(path):
        raise FileNotFoundError("simulated 404")

    with patch.object(exporter_mod, "fetch_json", side_effect=fake_fetch):
        # Must not raise
        exporter_mod.update_polar(40.0, -105.0)

    assert _polar_samples(fresh_polar_gauge) == []


def test_update_polar_survives_malformed_outline(fresh_polar_gauge):
    def fake_fetch(path):
        return {"something": "else"}

    with patch.object(exporter_mod, "fetch_json", side_effect=fake_fetch):
        # Must not raise
        exporter_mod.update_polar(40.0, -105.0)

    assert _polar_samples(fresh_polar_gauge) == []
