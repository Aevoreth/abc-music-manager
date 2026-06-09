"""Unit tests for setlist delete and clear."""

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from abc_music_manager.db.play_log import log_play
from abc_music_manager.db.schema import create_schema, seed_defaults, _run_migrations
from abc_music_manager.db.setlist_repo import (
    add_setlist,
    add_setlist_item,
    clear_setlist,
    delete_setlist,
    list_setlists,
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


def test_add_setlist_inserts_at_top_of_folder() -> None:
    conn = _open_test_conn()
    first_id = add_setlist(conn, "First")
    second_id = add_setlist(conn, "Second")
    third_id = add_setlist(conn, "Third")

    setlists = list_setlists(conn)
    uncategorized = [s for s in setlists if s.folder_id is None]
    assert [s.id for s in uncategorized] == [third_id, second_id, first_id]
    assert [s.sort_order for s in uncategorized] == [0, 1, 2]
    conn.close()


def test_clear_setlist_removes_items_but_keeps_setlist() -> None:
    conn = _open_test_conn()
    song_id = _add_test_song(conn)
    setlist_id = add_setlist(conn, "My Set")
    add_setlist_item(conn, setlist_id, song_id, 0)

    clear_setlist(conn, setlist_id)

    assert len(list_setlists(conn)) == 1
    assert conn.execute("SELECT COUNT(*) FROM SetlistItem WHERE setlist_id = ?", (setlist_id,)).fetchone()[0] == 0
    conn.close()


def test_delete_setlist_with_play_history() -> None:
    conn = _open_test_conn()
    song_id = _add_test_song(conn)
    setlist_id = add_setlist(conn, "My Set")
    add_setlist_item(conn, setlist_id, song_id, 0)
    log_play(conn, song_id, context_setlist_id=setlist_id)

    delete_setlist(conn, setlist_id)

    assert list_setlists(conn) == []
    assert conn.execute("SELECT COUNT(*) FROM SetlistItem").fetchone()[0] == 0
    assert conn.execute("SELECT context_setlist_id FROM PlayLog").fetchone()[0] is None
    conn.close()
