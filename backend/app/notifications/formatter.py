"""Build notification messages from alerts. Produces per-channel renderings."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# Emoji + color per alert kind
_KIND_STYLE: dict[str, dict[str, Any]] = {
    "military":      {"emoji": "🎖️", "color": 0x8B0000, "title": "Military aircraft overhead"},
    "emergency":     {"emoji": "🆘", "color": 0xFF0000, "title": "EMERGENCY squawk"},
    "interesting":   {"emoji": "✨", "color": 0x6495ED, "title": "Interesting aircraft"},
    "watchlist":     {"emoji": "👀", "color": 0xFFA500, "title": "Watchlist aircraft"},
    "high_altitude": {"emoji": "🚀", "color": 0x9370DB, "title": "Unusually high altitude"},
}
_DEFAULT_STYLE = {"emoji": "✈️", "color": 0x888888, "title": "Aircraft alert"}

# MarkdownV2 special chars per https://core.telegram.org/bots/api#markdownv2-style
_TG_ESCAPE = "_*[]()~`>#+-=|{}.!"


def _escape_md(text: str | None) -> str:
    if not text:
        return ""
    out = []
    for ch in str(text):
        if ch in _TG_ESCAPE:
            out.append("\\")
        out.append(ch)
    return "".join(out)


def _fmt_ft(alt: int | None) -> str:
    if alt is None:
        return "—"
    return f"{alt:,} ft"


@dataclass
class FormattedMessage:
    kind_emoji: str
    title: str
    subtitle: str
    body_lines: list[str]
    photo_url: str | None
    dashboard_url: str
    plain_text: str
    telegram_text: str
    discord_embed: dict[str, Any]
    html_body: str


def format_message(
    alert: dict[str, Any],
    enrichment: dict[str, Any] | None,
    dashboard_url: str,
) -> FormattedMessage:
    """Render an alert for all three channels."""
    enrichment = enrichment or {}
    hex_code = alert.get("hex", "???")
    kind = alert.get("kind", "unknown")
    payload = alert.get("payload") or {}

    style = _KIND_STYLE.get(kind, _DEFAULT_STYLE)

    flight = payload.get("flight")
    reg = payload.get("registration")
    type_code = payload.get("type_code")
    squawk = payload.get("squawk")
    emergency = payload.get("emergency")
    alt_baro = payload.get("alt_baro")
    peak_alt_ft = payload.get("peak_alt_ft")
    previous_alt_ft = payload.get("previous_alt_ft")
    distance_nm = payload.get("distance_nm")
    is_renotify = bool(payload.get("renotify"))
    operator = enrichment.get("operator")
    photo_url = enrichment.get("photo_url")
    watchlist_label = enrichment.get("watchlist_label")

    # Title: prefer watchlist label if present, otherwise use the kind's default title
    if is_renotify and kind == "high_altitude":
        title = "Climbing higher — high altitude"
    else:
        title = watchlist_label or style["title"]

    # Subtitle: "RCH2034 · C17 · USAF" — omit missing parts
    subtitle_parts = [p for p in (flight, type_code, operator, reg) if p]
    subtitle = " · ".join(subtitle_parts) if subtitle_parts else hex_code

    # Body lines — only include what we have
    body_lines: list[str] = []
    if kind == "high_altitude":
        if is_renotify and previous_alt_ft is not None:
            body_lines.append(
                f"Climb: {_fmt_ft(previous_alt_ft)} → {_fmt_ft(alt_baro)}"
            )
        else:
            body_lines.append(f"Crossed at: {_fmt_ft(alt_baro)}")
        if peak_alt_ft is not None and peak_alt_ft != alt_baro:
            body_lines.append(f"Peak: {_fmt_ft(peak_alt_ft)}")
    else:
        body_lines.append(f"Alt: {_fmt_ft(alt_baro)}")
    if distance_nm is not None:
        body_lines.append(f"Dist: {distance_nm:.1f} nm")
    if squawk:
        tag = " (EMERGENCY)" if kind == "emergency" else ""
        body_lines.append(f"Squawk: {squawk}{tag}")
    if emergency and kind != "emergency":  # show if not already flagged
        body_lines.append(f"Emergency flag: {emergency}")
    body_lines.append(f"Hex: {hex_code}")

    deep_link = f"{dashboard_url.rstrip('/')}/?hex={hex_code}"

    # Plain text: for email subject line + text-only Telegram fallback
    plain_text = (
        f"{style['emoji']} {title}\n"
        f"{subtitle}\n\n"
        + "\n".join(body_lines)
        + f"\n\nView: {deep_link}"
    )

    # Telegram (MarkdownV2): bold title + monospace fields + clickable link
    telegram_text = (
        f"{style['emoji']} *{_escape_md(title)}*\n"
        f"{_escape_md(subtitle)}\n\n"
        + "\n".join(_escape_md(line) for line in body_lines)
        + f"\n\n[View on dashboard]({_escape_md(deep_link)})"
    )

    # Discord embed payload (used inside the `embeds: [...]` list)
    discord_embed: dict[str, Any] = {
        "title": f"{style['emoji']} {title}",
        "description": f"**{subtitle}**\n\n" + "\n".join(body_lines),
        "color": style["color"],
        "url": deep_link,
    }
    if photo_url:
        discord_embed["image"] = {"url": photo_url}

    # HTML body for email
    html_photo = f'<img src="{photo_url}" alt="aircraft" style="max-width:400px;border-radius:4px;margin:8px 0">' if photo_url else ""
    html_body = (
        f"<html><body style=\"font-family:system-ui,sans-serif\">"
        f"<h2 style=\"margin-bottom:4px\">{style['emoji']} {title}</h2>"
        f"<div style=\"color:#555;font-size:14px;margin-bottom:12px\">{subtitle}</div>"
        f"{html_photo}"
        f"<ul style=\"line-height:1.7\">"
        + "".join(f"<li>{line}</li>" for line in body_lines)
        + f"</ul>"
        f"<p><a href=\"{deep_link}\">View on dashboard</a></p>"
        f"</body></html>"
    )

    return FormattedMessage(
        kind_emoji=style["emoji"],
        title=title,
        subtitle=subtitle,
        body_lines=body_lines,
        photo_url=photo_url,
        dashboard_url=deep_link,
        plain_text=plain_text,
        telegram_text=telegram_text,
        discord_embed=discord_embed,
        html_body=html_body,
    )
