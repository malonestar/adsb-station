"""Parse readsb aircraft.json into normalized AircraftState records."""

from __future__ import annotations

from datetime import UTC, datetime
from math import asin, atan2, cos, degrees, radians, sin, sqrt
from typing import Any

from app.config import settings
from app.enrichment.classifier import is_known_interesting, is_known_military
from app.readsb.schema import AircraftState

# readsb db_flags bitmask constants
DB_FLAG_MILITARY = 0x01
DB_FLAG_INTERESTING = 0x02
DB_FLAG_PIA = 0x04
DB_FLAG_LADD = 0x08

# Emergency squawks
_EMERGENCY_SQUAWKS = {"7500", "7600", "7700"}

# Earth radius in nautical miles for haversine
_EARTH_RADIUS_NM = 3440.065


def haversine_nm(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in nautical miles."""
    phi1, phi2 = radians(lat1), radians(lat2)
    dphi = radians(lat2 - lat1)
    dlam = radians(lon2 - lon1)
    a = sin(dphi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(dlam / 2) ** 2
    return 2 * _EARTH_RADIUS_NM * asin(sqrt(a))


def bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Initial bearing from point 1 → point 2 in degrees (0–360)."""
    phi1, phi2 = radians(lat1), radians(lat2)
    dlam = radians(lon2 - lon1)
    y = sin(dlam) * cos(phi2)
    x = cos(phi1) * sin(phi2) - sin(phi1) * cos(phi2) * cos(dlam)
    return (degrees(atan2(y, x)) + 360) % 360


def _strip(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    return s or None


def parse_aircraft(raw: dict[str, Any], now: datetime | None = None) -> AircraftState:
    """Convert a single raw readsb aircraft dict → AircraftState."""
    now = now or datetime.now(UTC)

    hex_code = str(raw["hex"]).lower()
    flight = _strip(raw.get("flight"))
    squawk = _strip(raw.get("squawk"))
    emergency = _strip(raw.get("emergency"))
    db_flags = int(raw.get("dbFlags", 0))

    lat = raw.get("lat")
    lon = raw.get("lon")

    distance_nm: float | None = None
    bearing: float | None = None
    if lat is not None and lon is not None:
        distance_nm = haversine_nm(settings.feeder_lat, settings.feeder_lon, lat, lon)
        bearing = bearing_deg(settings.feeder_lat, settings.feeder_lon, lat, lon)

    is_emergency = (
        (squawk in _EMERGENCY_SQUAWKS)
        or (emergency is not None and emergency.lower() not in ("", "none"))
    )

    return AircraftState(
        hex=hex_code,
        flight=flight,
        registration=_strip(raw.get("r")),
        type_code=_strip(raw.get("t")),
        category=_strip(raw.get("category")),
        lat=lat,
        lon=lon,
        alt_baro=raw.get("alt_baro") if isinstance(raw.get("alt_baro"), int) else None,
        alt_geom=raw.get("alt_geom") if isinstance(raw.get("alt_geom"), int) else None,
        gs=raw.get("gs"),
        tas=raw.get("tas"),
        mach=raw.get("mach"),
        track=raw.get("track"),
        true_heading=raw.get("true_heading"),
        mag_heading=raw.get("mag_heading"),
        baro_rate=raw.get("baro_rate"),
        geom_rate=raw.get("geom_rate"),
        squawk=squawk,
        emergency=emergency,
        messages=int(raw.get("messages", 0)),
        seen=float(raw.get("seen", 0.0)),
        seen_pos=raw.get("seen_pos"),
        rssi=raw.get("rssi"),
        db_flags=db_flags,
        distance_nm=distance_nm,
        bearing_deg=bearing,
        is_military=bool(db_flags & DB_FLAG_MILITARY) or is_known_military(hex_code),
        is_interesting=bool(db_flags & DB_FLAG_INTERESTING) or is_known_interesting(hex_code),
        is_pia=bool(db_flags & DB_FLAG_PIA),
        is_emergency=is_emergency,
        updated_at=now,
    )


def parse_snapshot(raw: dict[str, Any], now: datetime | None = None) -> list[AircraftState]:
    """Convert an entire readsb aircraft.json payload → list of AircraftState."""
    now = now or datetime.now(UTC)
    aircraft_list = raw.get("aircraft", []) or []
    out: list[AircraftState] = []
    for entry in aircraft_list:
        try:
            out.append(parse_aircraft(entry, now=now))
        except (KeyError, ValueError, TypeError):
            # Skip malformed rows but don't crash the poll
            continue
    return out
