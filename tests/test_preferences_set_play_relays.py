"""Tests for Set Play relay preference list and migration."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture
def data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Isolate preferences.json via ABC_MUSIC_MANAGER_DATA."""
    monkeypatch.setenv("ABC_MUSIC_MANAGER_DATA", str(tmp_path))
    (tmp_path / "abc_music_manager.sqlite").write_bytes(b"")
    return tmp_path


def test_migrate_legacy_set_play_relay_url(data_dir: Path) -> None:
    prefs_path = data_dir / "preferences.json"
    prefs_path.write_text(
        json.dumps({"set_play_relay_url": "wss://example.workers.dev"}),
        encoding="utf-8",
    )
    from abc_music_manager.services.preferences import (
        get_active_set_play_relay_url,
        get_set_play_relays,
        load_preferences,
    )

    relays = get_set_play_relays()
    assert len(relays) == 1
    assert relays[0]["name"] == "Default"
    assert relays[0]["url"] == "wss://example.workers.dev"
    assert get_active_set_play_relay_url() == "wss://example.workers.dev"

    prefs = load_preferences()
    assert "set_play_relay_url" not in prefs
    assert "set_play_relays" in prefs


def test_get_active_set_play_relay_url_fallback_selection(data_dir: Path) -> None:
    from abc_music_manager.services.preferences import (
        get_active_set_play_relay_url,
        set_set_play_relays,
        set_set_play_selected_relay_id,
    )

    set_set_play_relays(
        [
            {"id": "a", "name": "First", "url": "wss://one.example"},
            {"id": "b", "name": "Second", "url": "wss://two.example"},
        ]
    )
    set_set_play_selected_relay_id("b")
    assert get_active_set_play_relay_url() == "wss://two.example"

    set_set_play_selected_relay_id("missing")
    assert get_active_set_play_relay_url() == "wss://one.example"


def test_empty_relays_active_url(data_dir: Path) -> None:
    from abc_music_manager.services.preferences import get_active_set_play_relay_url

    assert get_active_set_play_relay_url() == ""
