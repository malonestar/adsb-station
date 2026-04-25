"""Tests for the notification message formatter."""

from app.notifications.formatter import format_message


def _base_alert() -> dict:
    return {
        "hex": "ae0123",
        "kind": "military",
        "triggered_at": "2026-04-21T15:30:00+00:00",
        "payload": {
            "flight": "RCH2034",
            "registration": "23-1534",
            "type_code": "C17",
            "squawk": "1234",
            "emergency": None,
            "alt_baro": 34000,
            "distance_nm": 12.3,
            "lat": 39.7,
            "lon": -104.9,
        },
    }


def test_military_uses_combat_emoji_and_clear_title():
    msg = format_message(_base_alert(), enrichment=None, dashboard_url="http://pi")
    assert msg.kind_emoji == "🎖️"
    assert "Military" in msg.title
    assert "RCH2034" in msg.subtitle


def test_includes_altitude_and_distance_in_body():
    msg = format_message(_base_alert(), enrichment=None, dashboard_url="http://pi")
    body = "\n".join(msg.body_lines)
    assert "34,000 ft" in body
    assert "12" in body  # distance_nm rounded


def test_emergency_uses_siren_and_squawk():
    alert = _base_alert()
    alert["kind"] = "emergency"
    alert["payload"]["squawk"] = "7700"
    msg = format_message(alert, enrichment=None, dashboard_url="http://pi")
    assert msg.kind_emoji == "🆘"
    assert "7700" in "\n".join(msg.body_lines)


def test_watchlist_includes_label_if_enrichment_provides():
    alert = _base_alert()
    alert["kind"] = "watchlist"
    enrichment = {"operator": "Government", "photo_url": None, "watchlist_label": "SAM (Air Force One)"}
    msg = format_message(alert, enrichment=enrichment, dashboard_url="http://pi")
    assert msg.kind_emoji == "👀"
    assert "SAM" in msg.title or "SAM" in msg.subtitle


def test_high_altitude_uses_rocket_and_altitude():
    alert = _base_alert()
    alert["kind"] = "high_altitude"
    alert["payload"]["alt_baro"] = 52000
    msg = format_message(alert, enrichment=None, dashboard_url="http://pi")
    assert msg.kind_emoji == "🚀"
    assert "52,000" in "\n".join(msg.body_lines)


def test_interesting_uses_sparkles():
    alert = _base_alert()
    alert["kind"] = "interesting"
    msg = format_message(alert, enrichment=None, dashboard_url="http://pi")
    assert msg.kind_emoji == "✨"


def test_photo_url_carries_through_when_present():
    alert = _base_alert()
    enrichment = {"operator": "USAF", "photo_url": "https://example.com/plane.jpg", "watchlist_label": None}
    msg = format_message(alert, enrichment=enrichment, dashboard_url="http://pi")
    assert msg.photo_url == "https://example.com/plane.jpg"


def test_dashboard_url_uses_hex_query():
    msg = format_message(_base_alert(), enrichment=None, dashboard_url="http://192.168.0.113")
    assert msg.dashboard_url == "http://192.168.0.113/?hex=ae0123"


def test_telegram_markdown_escapes_special_chars():
    """Telegram MarkdownV2 requires escaping . - ! etc in plain text fields."""
    alert = _base_alert()
    alert["payload"]["flight"] = "AF-1.LEADER"
    msg = format_message(alert, enrichment=None, dashboard_url="http://pi")
    # Telegram-specific encoded text must escape dots and dashes
    assert "\\." in msg.telegram_text or "\\-" in msg.telegram_text


def test_discord_embed_has_title_and_color():
    msg = format_message(_base_alert(), enrichment=None, dashboard_url="http://pi")
    assert "title" in msg.discord_embed
    assert "color" in msg.discord_embed


def test_html_body_contains_key_fields():
    msg = format_message(_base_alert(), enrichment=None, dashboard_url="http://pi")
    assert "<html" in msg.html_body.lower()
    assert "RCH2034" in msg.html_body
    assert "34,000" in msg.html_body


def test_missing_fields_do_not_crash():
    """If callsign / type are None, formatter produces reasonable fallback text."""
    alert = {
        "hex": "abc123",
        "kind": "watchlist",
        "triggered_at": "2026-04-21T15:30:00+00:00",
        "payload": {},
    }
    msg = format_message(alert, enrichment=None, dashboard_url="http://pi")
    assert "abc123" in msg.subtitle  # falls back to hex
    assert msg.plain_text  # non-empty


# --- high_altitude A+B+C: label, peak, renotify ---


def test_high_altitude_labels_alt_as_crossed_at():
    """A: trigger-time alt is labeled honestly as 'Crossed at', not 'Alt'."""
    alert = _base_alert()
    alert["kind"] = "high_altitude"
    alert["payload"]["alt_baro"] = 45_025
    alert["payload"]["peak_alt_ft"] = 45_025
    msg = format_message(alert, enrichment=None, dashboard_url="http://pi")
    body = "\n".join(msg.body_lines)
    assert "Crossed at: 45,025 ft" in body
    # Don't show a redundant Peak line when peak == alt at trigger
    assert "Peak:" not in body


def test_high_altitude_shows_peak_when_higher_than_trigger():
    """B: when payload carries a higher peak, show it."""
    alert = _base_alert()
    alert["kind"] = "high_altitude"
    alert["payload"]["alt_baro"] = 45_025
    alert["payload"]["peak_alt_ft"] = 60_000
    msg = format_message(alert, enrichment=None, dashboard_url="http://pi")
    body = "\n".join(msg.body_lines)
    assert "Crossed at: 45,025 ft" in body
    assert "Peak: 60,000 ft" in body


def test_high_altitude_renotify_uses_climb_phrasing():
    """C: a renotify event uses 'Climb: X → Y' phrasing and 'Climbing higher' title."""
    alert = _base_alert()
    alert["kind"] = "high_altitude"
    alert["payload"] = {
        "flight": "NASA928",
        "alt_baro": 56_000,
        "peak_alt_ft": 56_000,
        "previous_alt_ft": 45_025,
        "renotify": True,
    }
    msg = format_message(alert, enrichment=None, dashboard_url="http://pi")
    body = "\n".join(msg.body_lines)
    assert "Climb: 45,025 ft → 56,000 ft" in body
    assert "Climbing higher" in msg.title
