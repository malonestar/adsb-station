"""Alert evaluator — emits alert.new / alert.cleared events based on state."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select, update

from app.alerts.watchlist import watchlist
from app.config import settings
from app.db.models import Alert
from app.db.session import session_scope
from app.events.bus import bus
from app.logging import get_logger
from app.readsb.schema import AircraftDelta, AircraftState

log = get_logger(__name__)

AlertKind = str  # "military" | "emergency" | "watchlist" | "interesting" | "high_altitude"


class AlertEvaluator:
    # How long an aircraft can be absent from the snapshot before we consider the
    # alert truly cleared. Matches the registry's stale-after window. Without this
    # grace period, brief ADS-B signal dropouts (common — even steady tracks have
    # sub-second gaps) would clear and re-trigger the alert on each blip, writing
    # dozens of rows for one incident. Cooldown suppresses notifications, but the
    # DB would still bloat.
    CLEAR_GRACE = timedelta(seconds=300)
    # If a (hex, kind) was cleared within this window and fires again, re-open
    # the existing row (null its cleared_at) instead of inserting a new one.
    # High-altitude long-range tracks have variable message cadence; a cleared
    # alert that reappears within this window is almost always the same pass,
    # not a fresh incident. Notifications are NOT re-fired on re-open (the
    # dispatcher's cooldown already guards that).
    REOPEN_WINDOW = timedelta(seconds=300)

    # For high_altitude alerts: re-notify (with cooldown override) when the
    # aircraft climbs at least this many feet above the last notification.
    # Captures the typical NASA WB-57 / U-2 climb-out where trigger fires at
    # ~45,025 but the aircraft eventually levels off at FL600.
    HIGH_ALT_CLIMB_RENOTIFY_FT = 10_000

    def __init__(self) -> None:
        # (hex, kind) → alert.id currently active
        self._active: dict[tuple[str, AlertKind], int] = {}
        # (hex, kind) → last time we saw this alert's trigger condition still true.
        # Used to apply CLEAR_GRACE so brief absences don't clear the alert.
        self._last_seen: dict[tuple[str, AlertKind], datetime] = {}
        # (hex, kind) → peak alt seen during the alert's active life. Updated
        # on every tick; when peak grows, the DB payload is overwritten so the
        # historical record reflects the actual peak (not the trigger-time alt).
        self._peak_alt: dict[tuple[str, AlertKind], int] = {}
        # (hex, kind) → last alt at which a notification was sent. Used to
        # decide whether to re-notify when the aircraft climbs significantly.
        self._last_notified_alt: dict[tuple[str, AlertKind], int] = {}
        self._started = False

    async def start(self) -> None:
        if self._started:
            return
        await watchlist.refresh()
        # Load any existing uncleared alerts so we don't double-emit
        async with session_scope() as s:
            rows = (
                await s.execute(select(Alert).where(Alert.cleared_at.is_(None)))
            ).scalars().all()
            now = datetime.now(UTC)
            for r in rows:
                key = (r.hex, r.kind)
                self._active[key] = r.id
                # Seed last_seen to now so we don't immediately clear uncleared alerts
                # that were loaded from the DB at startup.
                self._last_seen[key] = now
                # For high_altitude alerts: seed peak/last-notified from the
                # alert's payload so we don't fire a spurious renotify_climb
                # on the first tick post-restart (default-zero would compare
                # any alt against 0 and trip the +10k threshold).
                if r.kind == "high_altitude":
                    payload = r.payload or {}
                    peak = payload.get("peak_alt_ft") or payload.get("alt_baro")
                    if peak is not None:
                        self._peak_alt[key] = int(peak)
                        self._last_notified_alt[key] = int(peak)
        self._started = True
        log.info("alert_evaluator_started", active=len(self._active))

    async def stop(self) -> None:
        self._started = False

    async def on_delta(
        self,
        delta: AircraftDelta,
        states: list[AircraftState],
        now: datetime,
    ) -> None:
        if not self._started:
            return
        seen_alerts: set[tuple[str, AlertKind]] = set()
        for state in states:
            kinds = self._evaluate(state)
            for kind in kinds:
                key = (state.hex, kind)
                seen_alerts.add(key)
                self._last_seen[key] = now
                if key not in self._active:
                    await self._trigger(state, kind)
                elif kind == "high_altitude" and state.alt_baro is not None:
                    await self._maybe_update_peak_alt(state, key)

        # Only clear alerts whose condition hasn't been met for > CLEAR_GRACE.
        # Brief snapshot absences don't clear; an aircraft that truly left range
        # (or dropped below the trigger threshold for longer than CLEAR_GRACE) does.
        for key in list(self._active.keys()):
            if key in seen_alerts:
                continue
            last = self._last_seen.get(key, now)
            if now - last > self.CLEAR_GRACE:
                await self._clear(*key)

    def _evaluate(self, state: AircraftState) -> list[AlertKind]:
        kinds: list[AlertKind] = []
        if state.is_military:
            kinds.append("military")
        if state.is_emergency:
            kinds.append("emergency")
        if state.is_interesting:
            kinds.append("interesting")
        if state.alt_baro is not None and state.alt_baro > settings.alert_high_altitude_ft:
            kinds.append("high_altitude")
        # Watchlist match (hex, registration, type). Only fires the alert
        # pipeline when the matched entry has notify=True; passive entries
        # (notify=False) still flag aircraft on the watchlist tab via the
        # /api/watchlist/details intersection but don't write alerts or push
        # notifications.
        # Operator-kind entries are not matched here — operator data lives
        # in the catalog (enrichment-time), not in AircraftState. Operator
        # entries are passive-only in V1; see the +ADD modal warning.
        wl_match = (
            watchlist.match("hex", state.hex)
            or (state.registration and watchlist.match("reg", state.registration))
            or (state.type_code and watchlist.match("type", state.type_code))
        )
        if wl_match and wl_match.notify:
            kinds.append("watchlist")
        return kinds

    async def _trigger(self, state: AircraftState, kind: AlertKind) -> None:
        now = datetime.now(UTC)
        payload: dict[str, Any] = {
            "flight": state.flight,
            "registration": state.registration,
            "type_code": state.type_code,
            "squawk": state.squawk,
            "emergency": state.emergency,
            "alt_baro": state.alt_baro,
            "distance_nm": state.distance_nm,
            "lat": state.lat,
            "lon": state.lon,
        }
        if kind == "high_altitude" and state.alt_baro is not None:
            # Trigger-time alt and peak start equal; peak grows as the
            # aircraft climbs further (see _maybe_update_peak_alt).
            payload["peak_alt_ft"] = state.alt_baro
            self._peak_alt[(state.hex, kind)] = state.alt_baro
            self._last_notified_alt[(state.hex, kind)] = state.alt_baro
        async with session_scope() as s:
            # Re-open path: if the most recent row for this (hex, kind) was
            # cleared within REOPEN_WINDOW, null its cleared_at and re-use it.
            # Prevents one pass-through with brief signal dropouts from writing
            # many rows. Notifications are NOT re-published (dispatcher's
            # cooldown would suppress them anyway, but we skip the event too).
            recent = (
                await s.execute(
                    select(Alert)
                    .where(Alert.hex == state.hex, Alert.kind == kind)
                    .order_by(Alert.id.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            # SQLite (via aiosqlite) stores DateTime(timezone=True) columns but
            # returns naive datetimes on read — coerce to UTC before diffing.
            recent_cleared = recent.cleared_at if recent is not None else None
            if recent_cleared is not None and recent_cleared.tzinfo is None:
                recent_cleared = recent_cleared.replace(tzinfo=UTC)
            if (
                recent is not None
                and recent_cleared is not None
                and now - recent_cleared <= self.REOPEN_WINDOW
            ):
                await s.execute(
                    update(Alert)
                    .where(Alert.id == recent.id)
                    .values(cleared_at=None)
                )
                self._active[(state.hex, kind)] = recent.id
                log.info(
                    "alert_reopened",
                    hex=state.hex,
                    kind=kind,
                    alert_id=recent.id,
                    cleared_at=recent_cleared.isoformat(),
                    flight=state.flight,
                )
                return

            row = Alert(
                hex=state.hex,
                kind=kind,
                triggered_at=now,
                payload=payload,
            )
            s.add(row)
            await s.flush()
            await s.refresh(row)
            self._active[(state.hex, kind)] = row.id
        await bus.publish(
            "alert.new",
            {
                "id": row.id,
                "hex": state.hex,
                "kind": kind,
                "triggered_at": now.isoformat(),
                "payload": payload,
            },
        )
        log.info("alert_triggered", hex=state.hex, kind=kind, flight=state.flight)

    async def _maybe_update_peak_alt(
        self, state: AircraftState, key: tuple[str, AlertKind]
    ) -> None:
        """Track peak altitude during a high_altitude alert's active life.

        Updates DB payload when peak grows (cheap — only fires when alt
        actually exceeds current peak, ~3-6 times per climb-out, not per-tick).
        Re-fires the notification when the aircraft climbs by at least
        HIGH_ALT_CLIMB_RENOTIFY_FT above the last notified altitude.
        """
        if state.alt_baro is None:
            return
        current_peak = self._peak_alt.get(key, 0)
        if state.alt_baro <= current_peak:
            return
        # Peak grew: persist to DB and update in-memory cache.
        self._peak_alt[key] = state.alt_baro
        alert_id = self._active.get(key)
        if alert_id is None:
            return
        async with session_scope() as s:
            row = await s.get(Alert, alert_id)
            if row is None:
                return
            payload = dict(row.payload or {})
            payload["peak_alt_ft"] = state.alt_baro
            row.payload = payload
        # Re-notify on significant climb. Last-notified seeded at trigger time.
        last_notified = self._last_notified_alt.get(key, current_peak)
        if state.alt_baro - last_notified >= self.HIGH_ALT_CLIMB_RENOTIFY_FT:
            self._last_notified_alt[key] = state.alt_baro
            renotify_payload: dict[str, Any] = {
                "flight": state.flight,
                "registration": state.registration,
                "type_code": state.type_code,
                "squawk": state.squawk,
                "alt_baro": state.alt_baro,
                "peak_alt_ft": state.alt_baro,
                "distance_nm": state.distance_nm,
                "lat": state.lat,
                "lon": state.lon,
                "renotify": True,
                "previous_alt_ft": last_notified,
            }
            await bus.publish(
                "alert.renotify",
                {
                    "id": alert_id,
                    "hex": state.hex,
                    "kind": "high_altitude",
                    "triggered_at": datetime.now(UTC).isoformat(),
                    "payload": renotify_payload,
                },
            )
            log.info(
                "alert_renotify_climb",
                hex=state.hex,
                from_alt=last_notified,
                to_alt=state.alt_baro,
            )

    async def _clear(self, hex_code: str, kind: AlertKind) -> None:
        key = (hex_code, kind)
        alert_id = self._active.pop(key, None)
        self._last_seen.pop(key, None)
        self._peak_alt.pop(key, None)
        self._last_notified_alt.pop(key, None)
        if alert_id is None:
            return
        now = datetime.now(UTC)
        async with session_scope() as s:
            await s.execute(
                update(Alert).where(Alert.id == alert_id).values(cleared_at=now)
            )
        await bus.publish(
            "alert.cleared",
            {"id": alert_id, "hex": hex_code, "kind": kind, "cleared_at": now.isoformat()},
        )
        log.info("alert_cleared", hex=hex_code, kind=kind)


evaluator = AlertEvaluator()
