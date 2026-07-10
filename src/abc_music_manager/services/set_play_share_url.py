"""Build and parse Set Play share links (/playback?set=CODE)."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse

from .set_play_relay_http import normalize_relay_base_url, relay_https_origin


@dataclass(frozen=True)
class ParsedShareLink:
    """Relay WebSocket base URL and room code extracted from a share link or bare code."""

    relay_ws_url: str
    room_code: str


def relay_ws_origin(url: str) -> str:
    """Worker origin as wss:// (or ws://) — no trailing slash."""
    https = relay_https_origin(url)
    if https.startswith("https://"):
        return "wss://" + https[8:]
    if https.startswith("http://"):
        return "ws://" + https[7:]
    return "wss://" + https


def build_playback_share_url(relay_base_url: str, room_code: str) -> str:
    """https://host/playback?set=CODE for assistants (browser or paste into app)."""
    origin = relay_https_origin(relay_base_url)
    code = (room_code or "").strip().upper()
    return f"{origin}/playback?set={code}"


def _looks_like_url(text: str) -> bool:
    low = text.lower()
    return low.startswith(("http://", "https://", "ws://", "wss://"))


def _normalize_url_for_parse(text: str) -> str:
    low = text.lower()
    if low.startswith("wss://"):
        return "https://" + text[6:]
    if low.startswith("ws://"):
        return "http://" + text[5:]
    return text


def parse_share_or_code(
    text: str,
    *,
    fallback_relay_url: str | None = None,
) -> ParsedShareLink | None:
    """
    Parse a playback share URL or a bare room code.

    - Full URL: extract host + ``set`` (or ``code``) query param, or ``/api/rooms/CODE``.
    - Bare code: requires ``fallback_relay_url`` (active Settings relay).
    """
    raw = (text or "").strip()
    if not raw:
        return None

    if _looks_like_url(raw):
        try:
            parsed = urlparse(_normalize_url_for_parse(raw))
        except ValueError:
            return None
        if not parsed.netloc:
            return None
        qs = parse_qs(parsed.query)
        code = ""
        for key in ("set", "code"):
            vals = qs.get(key) or []
            if vals and str(vals[0]).strip():
                code = str(vals[0]).strip().upper()
                break
        if not code:
            # /api/rooms/CODE or /api/rooms/CODE/ws
            parts = [p for p in parsed.path.split("/") if p]
            for i, part in enumerate(parts):
                if part.lower() == "rooms" and i + 1 < len(parts):
                    code = parts[i + 1].strip().upper()
                    break
        if len(code) < 5:
            return None
        scheme = "https" if parsed.scheme in ("https", "wss", "") else "http"
        origin = f"{scheme}://{parsed.netloc}"
        return ParsedShareLink(relay_ws_url=relay_ws_origin(origin), room_code=code)

    code = "".join(c for c in raw.upper() if c.isalnum())
    if len(code) < 5:
        return None
    base = normalize_relay_base_url(fallback_relay_url or "")
    if not base:
        return None
    return ParsedShareLink(relay_ws_url=relay_ws_origin(base), room_code=code)
