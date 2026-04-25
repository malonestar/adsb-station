"""Pydantic schemas for readsb input and our normalized AircraftState."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AircraftState(BaseModel):
    """Normalized aircraft record. All downstream consumers use this shape."""

    model_config = ConfigDict(extra="ignore")

    hex: str
    flight: str | None = None
    registration: str | None = None
    type_code: str | None = None
    category: str | None = None

    lat: float | None = None
    lon: float | None = None
    alt_baro: int | None = None
    alt_geom: int | None = None
    gs: float | None = None
    tas: float | None = None
    mach: float | None = None
    track: float | None = None
    true_heading: float | None = None
    mag_heading: float | None = None
    baro_rate: int | None = None
    geom_rate: int | None = None

    squawk: str | None = None
    emergency: str | None = None

    messages: int = 0
    seen: float = 0.0
    seen_pos: float | None = None
    rssi: float | None = None

    db_flags: int = 0

    # Derived at parse time
    distance_nm: float | None = None
    bearing_deg: float | None = None
    is_military: bool = False
    is_interesting: bool = False
    is_pia: bool = False
    is_emergency: bool = False

    updated_at: datetime


class ReceiverInfo(BaseModel):
    """Static station metadata from readsb receiver.json."""

    model_config = ConfigDict(extra="ignore")

    lat: float
    lon: float
    version: str | None = None
    refresh: int = 1000


class AircraftDelta(BaseModel):
    """Change set produced by the registry between ticks."""

    added: list[AircraftState] = Field(default_factory=list)
    updated: list[AircraftState] = Field(default_factory=list)
    removed: list[str] = Field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        return bool(self.added or self.updated or self.removed)
