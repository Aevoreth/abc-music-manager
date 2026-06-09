"""Unit tests for replace_player_in_band_layout."""

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from abc_music_manager.db.band_repo import (
    add_band,
    add_band_layout,
    add_band_member,
    get_export_column_order,
    list_layout_slots,
    replace_player_in_band_layout,
    set_export_column_order,
    set_layout_slot,
)
from abc_music_manager.db.player_repo import add_player, set_player_instrument
from abc_music_manager.db.schema import create_schema, seed_defaults, _run_migrations
from abc_music_manager.db.setlist_repo import (
    add_setlist,
    add_setlist_item,
    get_setlist_band_assignments,
    upsert_setlist_band_assignment,
)
from abc_music_manager.db.song_layout_repo import (
    add_song_layout,
    get_song_layout_assignments,
    set_song_layout_assignment,
)


def _open_test_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    create_schema(conn)
    _run_migrations(conn)
    seed_defaults(conn)
    return conn


def _add_test_song(conn: sqlite3.Connection) -> int:
    conn.execute(
        """INSERT INTO Song (title, composers, duration_seconds, transcriber, rating, status_id, notes, lyrics,
           last_played_at, total_plays, parts, created_at, updated_at)
           VALUES (?, ?, ?, NULL, NULL, NULL, NULL, NULL, NULL, 0, ?, datetime('now'), datetime('now'))""",
        ("Test Song", "Composer", 60, "[]"),
    )
    conn.commit()
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def _first_instrument_id(conn: sqlite3.Connection) -> int:
    conn.execute(
        "INSERT INTO Instrument (name, alternative_names, created_at, updated_at) VALUES (?, NULL, datetime('now'), datetime('now'))",
        ("Lute",),
    )
    conn.commit()
    return int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])


def test_replace_player_transfers_slot_and_assignments() -> None:
    conn = _open_test_conn()
    band_id = add_band(conn, "Test Band")
    layout_id = add_band_layout(conn, band_id, "Default")
    player_a = add_player(conn, "Alice")
    player_b = add_player(conn, "Bob")
    add_band_member(conn, band_id, player_a)
    set_layout_slot(conn, layout_id, player_a, 2, 3)
    set_export_column_order(conn, layout_id, [player_a])

    instrument_id = _first_instrument_id(conn)
    set_player_instrument(conn, player_a, instrument_id, has_instrument=True)
    set_player_instrument(conn, player_b, instrument_id, has_instrument=False)

    song_id = _add_test_song(conn)
    song_layout_id = add_song_layout(conn, song_id, layout_id, "Default")
    set_song_layout_assignment(conn, song_layout_id, player_a, 1)

    setlist_id = add_setlist(conn, "Test Set")
    item_id = add_setlist_item(conn, setlist_id, song_id, 0, song_layout_id=song_layout_id)
    upsert_setlist_band_assignment(conn, item_id, player_a, 2)

    replace_player_in_band_layout(conn, layout_id, band_id, player_a, player_b)

    slots = list_layout_slots(conn, layout_id)
    assert len(slots) == 1
    assert slots[0].player_id == player_b
    assert slots[0].x == 2
    assert slots[0].y == 3

    song_assigns = {a.player_id: a.part_number for a in get_song_layout_assignments(conn, song_layout_id)}
    assert player_a not in song_assigns
    assert song_assigns[player_b] == 1

    setlist_assigns = get_setlist_band_assignments(conn, item_id)
    assert player_a not in setlist_assigns
    assert setlist_assigns[player_b] == 2

    assert get_export_column_order(conn, layout_id) == [player_b]

    a_has = conn.execute(
        "SELECT has_instrument FROM PlayerInstrument WHERE player_id = ? AND instrument_id = ?",
        (player_a, instrument_id),
    ).fetchone()
    b_has = conn.execute(
        "SELECT has_instrument FROM PlayerInstrument WHERE player_id = ? AND instrument_id = ?",
        (player_b, instrument_id),
    ).fetchone()
    assert a_has is not None and a_has[0] == 1
    assert b_has is not None and b_has[0] == 0

    conn.close()


def test_replace_player_rejects_new_player_already_on_layout() -> None:
    conn = _open_test_conn()
    band_id = add_band(conn, "Test Band")
    layout_id = add_band_layout(conn, band_id, "Default")
    player_a = add_player(conn, "Alice")
    player_b = add_player(conn, "Bob")
    set_layout_slot(conn, layout_id, player_a, 0, 0)
    set_layout_slot(conn, layout_id, player_b, 5, 5)

    with pytest.raises(ValueError, match="already on layout"):
        replace_player_in_band_layout(conn, layout_id, band_id, player_a, player_b)

    conn.close()


def test_replace_player_rejects_old_player_not_on_layout() -> None:
    conn = _open_test_conn()
    band_id = add_band(conn, "Test Band")
    layout_id = add_band_layout(conn, band_id, "Default")
    player_a = add_player(conn, "Alice")
    player_b = add_player(conn, "Bob")

    with pytest.raises(ValueError, match="not on layout"):
        replace_player_in_band_layout(conn, layout_id, band_id, player_a, player_b)

    conn.close()
