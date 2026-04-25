"""Enrichment coordinator — fires hexdb + planespotters + route lookups."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, text

from app.db.models import AircraftCatalog
from app.db.session import session_scope
from app.enrichment import adsblol, classifier, hexdb, planespotters
from app.events.bus import bus
from app.logging import get_logger
from app.readsb.schema import AircraftState

log = get_logger(__name__)


class EnrichmentCoordinator:
    """Kicks off enrichment jobs for each newly-seen hex (or callsign)."""

    def __init__(self, *, concurrency: int = 4) -> None:
        self._semaphore = asyncio.Semaphore(concurrency)
        self._inflight_hex: set[str] = set()
        self._inflight_callsign: set[str] = set()
        self._tasks: set[asyncio.Task[None]] = set()

    async def start(self) -> None:
        await classifier.load_from_catalog()
        log.info("enrichment_coordinator_started")

    async def stop(self) -> None:
        for t in list(self._tasks):
            t.cancel()
        self._tasks.clear()
        log.info("enrichment_coordinator_stopped")

    def submit(self, state: AircraftState) -> None:
        """Public entrypoint — called from poller callback for each known aircraft."""
        if state.hex not in self._inflight_hex:
            self._inflight_hex.add(state.hex)
            self._spawn(self._enrich_hex(state))
        if state.flight and state.flight not in self._inflight_callsign:
            self._inflight_callsign.add(state.flight)
            self._spawn(self._enrich_route(state.hex, state.flight))

    def _spawn(self, coro) -> None:  # type: ignore[no-untyped-def]
        t = asyncio.create_task(coro)
        self._tasks.add(t)
        t.add_done_callback(self._tasks.discard)

    async def _enrich_hex(self, state: AircraftState) -> None:
        async with self._semaphore:
            try:
                # Run hexdb and planespotters in parallel
                hx, photo = await asyncio.gather(
                    hexdb.lookup(state.hex),
                    planespotters.lookup(state.hex),
                    return_exceptions=False,
                )
                payload = {"hex": state.hex}
                if hx:
                    payload.update(
                        {
                            "registration": hx.get("registration") or state.registration,
                            "type_code": hx.get("type_code") or state.type_code,
                            "operator": hx.get("operator"),
                            "type_name": hx.get("type_name"),
                            "manufacturer": hx.get("manufacturer"),
                        }
                    )
                if photo:
                    payload.update(
                        {
                            "photo_url": photo.get("photo_url"),
                            "photo_thumb_url": photo.get("photo_thumb_url"),
                            "photo_photographer": photo.get("photo_photographer"),
                            "photo_link": photo.get("photo_link"),
                        }
                    )
                await self._upsert_catalog(state, payload)
                if len(payload) > 1:
                    await bus.publish("aircraft.enriched", payload)
            except Exception:  # noqa: BLE001
                log.exception("enrich_hex_failed", hex=state.hex)
            finally:
                self._inflight_hex.discard(state.hex)

    async def enrich_cold(self, hex_code: str) -> dict[str, Any] | None:
        """Enrich a hex that has never been seen live.

        Used when a user manually adds a hex to the watchlist before the
        aircraft has appeared in the receiver's range. Hits hexdb +
        planespotters once and creates a stub catalog row with the resolved
        registration/type/operator/photo. Returns the merged payload so the
        caller can surface what was found.
        """
        hex_lc = hex_code.lower()
        if hex_lc in self._inflight_hex:
            return None
        self._inflight_hex.add(hex_lc)
        try:
            async with self._semaphore:
                hx, photo = await asyncio.gather(
                    hexdb.lookup(hex_lc),
                    planespotters.lookup(hex_lc),
                    return_exceptions=False,
                )
                payload: dict[str, Any] = {"hex": hex_lc}
                if hx:
                    payload.update(
                        {
                            "registration": hx.get("registration"),
                            "type_code": hx.get("type_code"),
                            "operator": hx.get("operator"),
                            "type_name": hx.get("type_name"),
                            "manufacturer": hx.get("manufacturer"),
                        }
                    )
                if photo:
                    payload.update(
                        {
                            "photo_url": photo.get("photo_url"),
                            "photo_thumb_url": photo.get("photo_thumb_url"),
                            "photo_photographer": photo.get("photo_photographer"),
                            "photo_link": photo.get("photo_link"),
                        }
                    )
                # Upsert a stub row. Use epoch timestamps + seen_count=0 as the
                # "never observed live" marker — the frontend keys off seen_count==0.
                # When the aircraft is finally seen, _update_catalog_stats's gap
                # check passes (epoch >> 5min) and seen_count steps to 1.
                async with session_scope() as s:
                    row = await s.get(AircraftCatalog, hex_lc)
                    if row is None:
                        epoch = datetime(1970, 1, 1, tzinfo=UTC)
                        row = AircraftCatalog(
                            hex=hex_lc,
                            first_seen=epoch,
                            last_seen=epoch,
                            seen_count=0,
                        )
                        s.add(row)
                    row.registration = payload.get("registration") or row.registration
                    row.type_code = payload.get("type_code") or row.type_code
                    row.operator = payload.get("operator") or row.operator
                    row.photo_url = payload.get("photo_url") or row.photo_url
                    row.photo_thumb_url = payload.get("photo_thumb_url") or row.photo_thumb_url
                    row.photo_photographer = payload.get("photo_photographer") or row.photo_photographer
                    row.photo_link = payload.get("photo_link") or row.photo_link
                    op_mil, op_int = classifier.classify_operator(row.operator)
                    if op_mil:
                        row.is_military = True
                    if op_int:
                        row.is_interesting = True
                    if row.is_military or row.is_interesting:
                        classifier.remember(
                            hex_lc, military=row.is_military, interesting=row.is_interesting
                        )
                log.info("cold_enriched", hex=hex_lc, found_keys=list(payload.keys()))
                return payload
        except Exception:  # noqa: BLE001
            log.exception("cold_enrich_failed", hex=hex_lc)
            return None
        finally:
            self._inflight_hex.discard(hex_lc)

    async def _enrich_route(self, hex_code: str, callsign: str) -> None:
        # Use route_service (3-tier cascade) instead of single-source adsblol
        # so results land in the route_cache table. Downstream consumers —
        # airports board, /api/aircraft/{hex}/route, alerts payloads — all
        # read from route_cache, so without this they only see route data
        # for aircraft a user has manually clicked. With it, every callsign
        # we observe gets its origin/destination resolved exactly once
        # (cache hits afterward), populating the airport boards correctly.
        from app.enrichment.route import route_service

        async with self._semaphore:
            try:
                route_info = await route_service.get_route(callsign)
                if route_info is not None and route_info.source != "not_found":
                    await bus.publish(
                        "aircraft.enriched",
                        {
                            "hex": hex_code,
                            "callsign": callsign,
                            "route": route_info.to_dict(),
                        },
                    )
            except Exception:  # noqa: BLE001
                log.exception("enrich_route_failed", callsign=callsign)
            finally:
                self._inflight_callsign.discard(callsign)

    async def _upsert_catalog(self, state: AircraftState, payload: dict[str, Any]) -> None:
        now = datetime.now(UTC)
        async with session_scope() as s:
            row = await s.get(AircraftCatalog, state.hex)
            if row is None:
                row = AircraftCatalog(
                    hex=state.hex,
                    first_seen=now,
                    last_seen=now,
                    seen_count=1,
                    category=state.category,
                    is_military=state.is_military,
                    is_interesting=state.is_interesting,
                    is_pia=state.is_pia,
                )
                s.add(row)
            row.last_seen = now
            row.registration = payload.get("registration") or row.registration
            row.type_code = payload.get("type_code") or row.type_code
            row.operator = payload.get("operator") or row.operator
            row.photo_url = payload.get("photo_url") or row.photo_url
            row.photo_thumb_url = payload.get("photo_thumb_url") or row.photo_thumb_url
            row.photo_photographer = payload.get("photo_photographer") or row.photo_photographer
            row.photo_link = payload.get("photo_link") or row.photo_link
            row.category = state.category or row.category
            # Operator-string classification augments readsb's dbFlags. Sticky
            # bits — once True, never flipped back to False here.
            op_mil, op_int = classifier.classify_operator(row.operator)
            row.is_military = row.is_military or state.is_military or op_mil
            row.is_interesting = row.is_interesting or state.is_interesting or op_int
            row.is_pia = row.is_pia or state.is_pia
            if row.is_military or row.is_interesting:
                classifier.remember(
                    state.hex,
                    military=row.is_military,
                    interesting=row.is_interesting,
                )

    async def on_delta(self, delta, states: list[AircraftState], now: datetime) -> None:
        for state in states:
            self.submit(state)
        # Roll forward running catalog stats for every currently-observed aircraft.
        # _upsert_catalog only runs at enrichment time (once per hex), so without
        # this pass seen_count / max_alt_ft / max_speed_kt / min_distance_nm
        # would be frozen at their initial values.
        await self._update_catalog_stats(states, now)

    # Gap (in seconds) between observations that counts as a new "sighting". An
    # aircraft tracked continuously counts as 1; if it drops off and returns after
    # this window, seen_count increments. 5 minutes captures genuine reappearances
    # (e.g., aircraft left range and came back) without double-counting brief ADS-B
    # signal dropouts.
    _SIGHTING_GAP_SECONDS = 300

    async def _update_catalog_stats(
        self, states: list[AircraftState], now: datetime
    ) -> None:
        if not states:
            return
        # Single transaction; per-row UPDATE with CASE expressions so NULLs don't
        # clobber prior non-null extremes. Rows that don't yet exist in the catalog
        # (pre-enrichment) are a no-op UPDATE — they'll start accumulating once
        # enrichment creates the row. seen_count increments only when the aircraft
        # returns after _SIGHTING_GAP_SECONDS of absence, so it reflects distinct
        # sightings rather than observation ticks.
        stmt = text(
            """
            UPDATE aircraft_catalog SET
                seen_count = CASE
                    WHEN last_seen IS NULL
                         OR (julianday(:now) - julianday(last_seen)) * 86400.0 >= :gap
                    THEN seen_count + 1
                    ELSE seen_count END,
                last_seen = :now,
                max_alt_ft = CASE
                    WHEN :alt IS NOT NULL
                         AND (max_alt_ft IS NULL OR :alt > max_alt_ft)
                    THEN :alt ELSE max_alt_ft END,
                max_speed_kt = CASE
                    WHEN :gs IS NOT NULL
                         AND (max_speed_kt IS NULL OR :gs > max_speed_kt)
                    THEN :gs ELSE max_speed_kt END,
                min_distance_nm = CASE
                    WHEN :dist IS NOT NULL
                         AND (min_distance_nm IS NULL OR :dist < min_distance_nm)
                    THEN :dist ELSE min_distance_nm END
            WHERE hex = :hex
            """
        )
        async with session_scope() as s:
            for state in states:
                await s.execute(
                    stmt,
                    {
                        "hex": state.hex,
                        "now": now,
                        "gap": self._SIGHTING_GAP_SECONDS,
                        "alt": state.alt_baro,
                        "gs": int(state.gs) if state.gs is not None else None,
                        "dist": state.distance_nm,
                    },
                )


coordinator = EnrichmentCoordinator()
