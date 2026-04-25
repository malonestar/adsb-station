"""Application settings loaded from ADSB_* environment variables."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=None,
        env_prefix="ADSB_",
        extra="ignore",
        case_sensitive=False,
    )

    # ─── Station location ───────────────────────────────────────────────
    feeder_lat: float = 39.7
    feeder_lon: float = -104.8
    feeder_alt_m: int = 1646
    feeder_name: str = "aurora-co"
    feeder_tz: str = "America/Denver"

    # ─── readsb integration ─────────────────────────────────────────────
    # Either point at a file path (dev) or an HTTP URL (Docker).
    # Docker compose sets ADSB_READSB_AIRCRAFT_URL to http://ultrafeeder/data/aircraft.json
    readsb_aircraft_url: str | None = "http://ultrafeeder/data/aircraft.json"
    readsb_receiver_url: str | None = "http://ultrafeeder/data/receiver.json"
    readsb_stats_url: str | None = "http://ultrafeeder/data/stats.json"
    readsb_json_path: Path = Path("/data/readsb/aircraft.json")
    receiver_json_path: Path = Path("/data/readsb/receiver.json")
    stats_json_path: Path = Path("/data/readsb/stats.json")
    poll_interval_s: float = 1.0

    # ─── Persistence ────────────────────────────────────────────────────
    db_path: Path = Path("/data/db/adsb.db")
    position_retention_days: int = 90
    position_flush_interval_s: float = 5.0

    # ─── External APIs ──────────────────────────────────────────────────
    hexdb_base: str = "https://hexdb.io/api/v1"
    planespotters_base: str = "https://api.planespotters.net/pub"
    opensky_base: str = "https://opensky-network.org/api"
    adsblol_base: str = "https://api.adsb.lol/v2"
    adsbdb_base: str = "https://api.adsbdb.com/v0"
    flightaware_aeroapi_base: str = "https://aeroapi.flightaware.com/aeroapi"
    flightaware_aeroapi_key: str | None = None
    http_timeout_s: float = 5.0
    enrichment_ttl_days: int = 90
    # Route-cache TTLs (hours). Hits cached longer than misses so unknowns can
    # repopulate when APIs add new routes.
    route_cache_hit_ttl_hours: int = 6
    route_cache_miss_ttl_hours: int = 1

    # ─── Circuit breaker ────────────────────────────────────────────────
    cb_failure_threshold: int = 5
    cb_reset_after_s: int = 60

    # ─── Docker (for feed health) ───────────────────────────────────────
    docker_socket: Path = Path("/var/run/docker.sock")

    # ─── Notifications (Phase 3B) ───────────────────────────────────────
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None
    discord_webhook_url: str | None = None
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_from: str | None = None
    smtp_to: str | None = None
    alert_cooldown_hours: int = 6
    alert_high_altitude_ft: int = 45000
    alert_quiet_hours_start: str | None = None
    alert_quiet_hours_end: str | None = None
    dashboard_base_url: str = "http://192.168.0.113"

    # ─── Logging ────────────────────────────────────────────────────────
    log_level: str = "INFO"
    log_json: bool = True


settings = Settings()
