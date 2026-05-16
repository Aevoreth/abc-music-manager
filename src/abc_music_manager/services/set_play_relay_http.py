"""HTTP client for Set Play Cloudflare relay (create room)."""

from __future__ import annotations

import json
import urllib.error
import urllib.request


def normalize_relay_base_url(url: str) -> str:
    """Strip accidental /api/rooms suffix if user pasted a full API path."""
    u = (url or "").strip().rstrip("/")
    low = u.lower()
    for suffix in ("/api/rooms/ws", "/api/rooms"):
        if low.endswith(suffix):
            u = u[: -len(suffix)].rstrip("/")
            low = u.lower()
    return u


def relay_https_origin(url: str) -> str:
    """Worker origin (https) for REST calls — no trailing slash."""
    u = normalize_relay_base_url(url)
    if u.startswith("wss://"):
        return "https://" + u[6:]
    if u.startswith("https://"):
        return u
    if u.startswith("http://"):
        return u
    return "https://" + u


def create_relay_room(base_url: str) -> tuple[str, str]:
    """
    POST /api/rooms -> (roomCode, leaderToken).
    Uses an explicit User-Agent; default Python-urllib UAs are often blocked by Cloudflare (403).
    """
    origin = relay_https_origin(base_url)
    full = origin + "/api/rooms"
    req = urllib.request.Request(
        full,
        data=b"{}",
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            # Avoid bare Python-urllib — Cloudflare Bot Fight / similar often returns 403.
            "User-Agent": "ABC-Music-Manager/1.0 (Set Play relay client; desktop)",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:800]
        hint = ""
        if e.code == 403:
            hint = (
                " Cloudflare (or a network filter) may be blocking non-browser clients. "
                "In Cloudflare Dashboard → Security, try lowering Bot Fight Mode for this zone, "
                "or add a WAF exception for POST /api/rooms on your worker. "
                "Also confirm the relay URL is only the worker host (e.g. wss://….workers.dev), not a path under a different app."
            )
        raise ValueError(f"HTTP {e.code} {e.reason}.{hint} Body: {body}") from e
    return str(data["roomCode"]), str(data["leaderToken"])
