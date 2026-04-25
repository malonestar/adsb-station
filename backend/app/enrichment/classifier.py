"""Operator-string classification for is_military / is_interesting flags.

readsb's static aircraft DB (`dbFlags & 0x01` for military, `& 0x02` for
interesting) misses a lot of small-fleet government aircraft — USAF DHC-6
parachute-team birds, RC-135 variants, NASA WB-57s, etc. This module
augments those flags by regex-matching the enriched operator string from
hexdb. Hits are cached per-hex in module-level sets so the parser can
consult them on every tick without hitting the DB.
"""

from __future__ import annotations

import re

from sqlalchemy import select, update

from app.db.models import AircraftCatalog
from app.db.session import session_scope
from app.logging import get_logger

log = get_logger(__name__)


# Case-insensitive. Each pattern matches ANYWHERE in the operator string.
_MILITARY_PATTERNS = [
    # US armed forces (every common phrasing)
    r"\b(?:united states|us|usa)\s+(?:air force|army|navy|marine|marines|coast guard)\b",
    r"\busaf\b", r"\busn\b", r"\busmc\b", r"\buscg\b",
    # Air National Guard (any state prefix)
    r"\bair national guard\b",
    # DoD umbrella
    r"\b(?:dod|department of defen[cs]e)\b",
    # CBP (federal law enforcement, P-3s + MQ-9s)
    r"\b(?:customs and border protection|cbp)\b",
    # Allied air arms — common ones likely to fly through CO airspace
    r"\broyal (?:air force|navy|canadian|australian|new zealand|netherlands|saudi|jordanian|thai)\b",
    r"\b(?:german|french|italian|spanish|polish|dutch|belgian|norwegian|swedish|danish|finnish)\s+(?:air force|army|navy)\b",
    r"\bluftwaffe\b", r"\barmée de l'?air\b", r"\baeronautica militare\b",
    r"\b(?:canadian|australian|israeli|japanese|korean|brazilian) (?:air force|defense force|defence force)\b",
    r"\bnato\b",
]

_INTERESTING_PATTERNS = [
    r"\bnasa\b", r"\bnational aeronautics\b",
    r"\bfaa\b", r"\bfederal aviation\b",
    r"\bnoaa\b",  # hurricane hunters etc.
    r"\b(?:doe|department of energy)\b",
    r"\bdarpa\b",
    r"\bus forest service\b",  # firefighting tankers
]

_MILITARY_RE = re.compile("|".join(_MILITARY_PATTERNS), re.IGNORECASE)
_INTERESTING_RE = re.compile("|".join(_INTERESTING_PATTERNS), re.IGNORECASE)


def classify_operator(operator: str | None) -> tuple[bool, bool]:
    """Returns (is_military, is_interesting) implied by the operator string."""
    if not operator:
        return False, False
    return bool(_MILITARY_RE.search(operator)), bool(_INTERESTING_RE.search(operator))


# In-memory caches consulted by the parser on every tick. Populated from the
# catalog at startup and grown by the enrichment coordinator as new operator
# strings resolve. O(1) hex lookup; sets are bounded by the size of the catalog.
known_military_hexes: set[str] = set()
known_interesting_hexes: set[str] = set()


def is_known_military(hex_code: str) -> bool:
    return hex_code.lower() in known_military_hexes


def is_known_interesting(hex_code: str) -> bool:
    return hex_code.lower() in known_interesting_hexes


def remember(hex_code: str, *, military: bool, interesting: bool) -> None:
    """Add a hex to the in-memory classification sets."""
    h = hex_code.lower()
    if military:
        known_military_hexes.add(h)
    if interesting:
        known_interesting_hexes.add(h)


async def load_from_catalog() -> None:
    """Populate the in-memory sets from existing catalog rows at startup."""
    async with session_scope() as s:
        rows = (
            await s.execute(
                select(AircraftCatalog.hex, AircraftCatalog.is_military, AircraftCatalog.is_interesting)
                .where((AircraftCatalog.is_military.is_(True)) | (AircraftCatalog.is_interesting.is_(True)))
            )
        ).all()
    mil = 0
    intr = 0
    for hex_code, is_mil, is_int in rows:
        h = hex_code.lower()
        if is_mil:
            known_military_hexes.add(h)
            mil += 1
        if is_int:
            known_interesting_hexes.add(h)
            intr += 1
    log.info("classifier_loaded", military=mil, interesting=intr)


async def backfill_from_catalog() -> None:
    """One-shot: re-classify every catalog row based on its operator string.

    Sets is_military/is_interesting where the regex matches; does NOT clear
    True flags that came from readsb's dbFlags (those stay sticky). Refreshes
    the in-memory sets as a side effect.
    """
    async with session_scope() as s:
        rows = (
            await s.execute(
                select(AircraftCatalog.hex, AircraftCatalog.operator,
                       AircraftCatalog.is_military, AircraftCatalog.is_interesting)
                .where(AircraftCatalog.operator.is_not(None))
            )
        ).all()
        promoted_mil = 0
        promoted_int = 0
        for hex_code, operator, was_mil, was_int in rows:
            mil, intr = classify_operator(operator)
            new_mil = was_mil or mil
            new_int = was_int or intr
            if new_mil != was_mil or new_int != was_int:
                await s.execute(
                    update(AircraftCatalog)
                    .where(AircraftCatalog.hex == hex_code)
                    .values(is_military=new_mil, is_interesting=new_int)
                )
                if new_mil and not was_mil:
                    promoted_mil += 1
                if new_int and not was_int:
                    promoted_int += 1
            remember(hex_code, military=new_mil, interesting=new_int)
    log.info(
        "classifier_backfill_complete",
        scanned=len(rows),
        promoted_military=promoted_mil,
        promoted_interesting=promoted_int,
    )
