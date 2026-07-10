"""Tests for Set Play share link build/parse helpers."""

from __future__ import annotations

from abc_music_manager.services.set_play_share_url import (
    build_playback_share_url,
    parse_share_or_code,
    relay_ws_origin,
)


def test_build_playback_share_url_from_wss() -> None:
    url = build_playback_share_url(
        "wss://abc-set-play-relay.example.workers.dev",
        "12AB3CD",
    )
    assert url == "https://abc-set-play-relay.example.workers.dev/playback?set=12AB3CD"


def test_build_playback_share_url_normalizes_code_case() -> None:
    url = build_playback_share_url("https://relay.example.com/", "ab12cd3")
    assert url == "https://relay.example.com/playback?set=AB12CD3"


def test_relay_ws_origin() -> None:
    assert relay_ws_origin("https://host.example") == "wss://host.example"
    assert relay_ws_origin("wss://host.example") == "wss://host.example"


def test_parse_share_link() -> None:
    parsed = parse_share_or_code(
        "https://abc-set-play-relay.example.workers.dev/playback?set=12AB3CD"
    )
    assert parsed is not None
    assert parsed.room_code == "12AB3CD"
    assert parsed.relay_ws_url == "wss://abc-set-play-relay.example.workers.dev"


def test_parse_wss_share_link() -> None:
    parsed = parse_share_or_code(
        "wss://relay.example.com/playback?set=ZZZZZZZ"
    )
    assert parsed is not None
    assert parsed.room_code == "ZZZZZZZ"
    assert parsed.relay_ws_url == "wss://relay.example.com"


def test_parse_api_rooms_path() -> None:
    parsed = parse_share_or_code(
        "https://relay.example.com/api/rooms/HELLO12/ws"
    )
    assert parsed is not None
    assert parsed.room_code == "HELLO12"
    assert parsed.relay_ws_url == "wss://relay.example.com"


def test_parse_bare_code_with_fallback_relay() -> None:
    parsed = parse_share_or_code(
        "12AB3CD",
        fallback_relay_url="wss://relay.example.com",
    )
    assert parsed is not None
    assert parsed.room_code == "12AB3CD"
    assert parsed.relay_ws_url == "wss://relay.example.com"


def test_parse_bare_code_without_relay_fails() -> None:
    assert parse_share_or_code("12AB3CD") is None


def test_parse_short_code_fails() -> None:
    assert parse_share_or_code("AB", fallback_relay_url="wss://x.example") is None
    assert parse_share_or_code("https://x.example/playback?set=AB") is None


def test_parse_empty() -> None:
    assert parse_share_or_code("") is None
    assert parse_share_or_code("   ") is None
