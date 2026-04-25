"""SMTP email adapter using aiosmtplib. Supports TLS on 465 and STARTTLS on 587.

Enabled when all of ADSB_SMTP_{HOST,USER,PASSWORD,FROM,TO} are set.
Honors quiet-hours window except for emergency-kind alerts.
"""

from __future__ import annotations

from datetime import datetime
from email.message import EmailMessage
from zoneinfo import ZoneInfo

import aiosmtplib

from app.config import settings
from app.logging import get_logger
from app.notifications.formatter import FormattedMessage
from app.notifications.quiet_hours import is_quiet

log = get_logger(__name__)


class EmailNotifier:
    def __init__(
        self,
        host: str,
        port: int,
        user: str,
        password: str,
        from_addr: str,
        to_addr: str,
    ) -> None:
        self._host = host
        self._port = port
        self._user = user
        self._password = password
        self._from = from_addr
        self._to = to_addr

    @classmethod
    def maybe_create(
        cls,
        host: str | None,
        port: int,
        user: str | None,
        password: str | None,
        from_addr: str | None,
        to_addr: str | None,
    ) -> "EmailNotifier | None":
        if not all([host, user, password, from_addr, to_addr]):
            return None
        return cls(host, port, user, password, from_addr, to_addr)  # type: ignore[arg-type]

    async def notify(self, msg: FormattedMessage, *, kind: str) -> None:
        # Quiet hours: skip unless this is an emergency
        if kind != "emergency":
            try:
                tz = ZoneInfo(settings.feeder_tz)
            except Exception:  # noqa: BLE001
                tz = None
            now_local = datetime.now(tz).time() if tz else datetime.now().time()
            if is_quiet(
                now_local,
                settings.alert_quiet_hours_start,
                settings.alert_quiet_hours_end,
            ):
                log.info("email_skipped_quiet_hours", title=msg.title)
                return

        email = EmailMessage()
        email["Subject"] = f"{msg.kind_emoji} ADS-B: {msg.title}"
        email["From"] = self._from
        email["To"] = self._to
        email.set_content(msg.plain_text)
        email.add_alternative(msg.html_body, subtype="html")

        # Port 465 = implicit TLS, port 587 = STARTTLS, anything else = plaintext
        use_tls = self._port == 465
        start_tls = self._port == 587

        await aiosmtplib.send(
            email,
            hostname=self._host,
            port=self._port,
            username=self._user,
            password=self._password,
            use_tls=use_tls,
            start_tls=start_tls,
            timeout=10.0,
        )
        log.info("email_notified", title=msg.title, to=self._to)

    @property
    def name(self) -> str:
        return "email"
