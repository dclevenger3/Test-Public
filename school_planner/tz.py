"""The family's timezone, set once from config.yaml. Feeds and APIs report UTC; kids live in local time."""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

_TZ: ZoneInfo | None = None


def set_timezone(name: str) -> None:
    global _TZ
    try:
        _TZ = ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        raise SystemExit(f"Unknown timezone '{name}' in config.yaml. Use an IANA name like America/New_York.")


def to_local(dt: datetime) -> datetime:
    """Convert an aware datetime to the configured timezone and drop tzinfo (the app works in naive local time)."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    target = _TZ or datetime.now().astimezone().tzinfo
    return dt.astimezone(target).replace(tzinfo=None)
