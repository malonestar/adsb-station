"""Interactive Telegram bot (long-polling) for ADS-B.

The bot reads commands from the single authorized chat (ADSB_TELEGRAM_CHAT_ID)
and dispatches them to handlers that query the live poller, the database, and
the enrichment services. It also supports reply-to-alert interactions: replying
to an alert message with keywords like 'watch' / 'mute' / 'info' performs an
action on the aircraft the alert was about.
"""
