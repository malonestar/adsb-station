"""One-shot seeder: populates the watchlist table on first startup.

No-op when the table already has entries. Intended to give the feature a
useful default set so it's immediately interesting on day one. User can edit
entries via POST /api/watchlist or direct DB edits later.

Sources for hex codes are public (ADS-B Exchange historical data, open
celebrity-jet trackers, warbird registries). Expect some entries to go stale
as aircraft are sold / re-registered — user can prune via API.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select

from app.db.models import Watchlist
from app.db.session import session_scope
from app.logging import get_logger

log = get_logger(__name__)


# (kind, value, label) — lowercase value, kind in {hex, reg, type, operator}.
_SEED: list[tuple[str, str, str]] = [
    # ─── US government / VIP heavies ─────────────────────────────────────
    ("hex", "adfdf9", "SAM (Air Force One — VC-25A 82-8000)"),
    ("hex", "adfdff", "SAM (Air Force One — VC-25A 92-9000)"),
    ("hex", "ae01d0", "USAF C-32 (VIP / SecState-class)"),
    ("hex", "ae01d1", "USAF C-32 (VIP / SecState-class)"),

    # ─── Known public executive / celeb jets (hex codes change over time) ─
    ("hex", "a835af", "Elon Musk jet (N628TS — G650ER)"),
    ("hex", "a5ecab", "Taylor Swift jet (N898TS — Falcon 7X)"),
    ("hex", "a95656", "Bill Gates jet (N194WM — BBJ)"),
    ("hex", "a18845", "Mark Zuckerberg jet (N68885 — G650)"),
    ("hex", "a0bfe0", "Jeff Bezos jet (N271DV — G650ER)"),

    # ─── Warbirds that still fly on the airshow circuit ─────────────────
    ("hex", "a17b3d", "B-17 Flying Fortress 'Yankee Lady'"),
    ("hex", "a6f2a5", "B-29 Superfortress 'FiFi'"),
    ("hex", "a8b6c4", "P-51 Mustang 'Crazy Horse'"),

    # ─── Rare / interesting TYPES (matches any aircraft of that type) ───
    ("type", "b2",   "B-2 Spirit stealth bomber"),
    ("type", "b52",  "B-52 Stratofortress"),
    ("type", "u2",   "U-2 Dragon Lady"),
    ("type", "sr71", "SR-71 Blackbird (museum-preserved)"),
    ("type", "c5m",  "C-5M Super Galaxy"),
    ("type", "e3tf", "E-3 Sentry (AWACS)"),
    ("type", "e6",   "E-6B Mercury (TACAMO)"),
    ("type", "rc135", "RC-135 Rivet Joint (SIGINT)"),
    ("type", "v22",  "V-22 Osprey"),
    ("type", "conc", "Concorde (museum-preserved)"),
    ("type", "an124","Antonov An-124 Ruslan"),
    ("type", "a388", "Airbus A380"),

    # ─── Operators of persistent interest ────────────────────────────────
    ("operator", "nasa", "NASA aircraft (any)"),
]


async def seed_watchlist_if_empty() -> int:
    """Insert seed entries if the watchlist table has zero rows. Returns
    the number of rows inserted (0 if already populated)."""
    async with session_scope() as s:
        existing = (await s.execute(select(Watchlist).limit(1))).scalar_one_or_none()
        if existing is not None:
            log.info("watchlist_seed_skipped_already_populated")
            return 0
        now = datetime.now(UTC)
        for kind, value, label in _SEED:
            s.add(
                Watchlist(
                    kind=kind,
                    value=value.lower(),
                    label=label,
                    created_at=now,
                )
            )
        await s.flush()
    log.info("watchlist_seeded", count=len(_SEED))
    return len(_SEED)
