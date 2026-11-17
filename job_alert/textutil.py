"""Small text helpers: HTML to plain text, ISO / epoch timestamps."""

from __future__ import annotations

import html
import re
from datetime import datetime, timezone

_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"[ \t\r\f\v]+")
_BLANKS = re.compile(r"\n{3,}")


def html_to_text(raw: str | None) -> str:
    """Rough HTML -> text. Handles Greenhouse's entity-escaped HTML too."""
    if not raw:
        return ""
    text = html.unescape(html.unescape(raw))  # Greenhouse escapes once on top of real HTML
    text = re.sub(r"(?i)<\s*(br|/p|/li|/h\d|/div)\s*/?>", "\n", text)
    text = _TAG.sub(" ", text)
    text = _WS.sub(" ", text)
    text = "\n".join(line.strip() for line in text.splitlines())
    return _BLANKS.sub("\n\n", text).strip()


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def from_epoch_ms(value: int | float | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromtimestamp(value / 1000, tz=timezone.utc)
