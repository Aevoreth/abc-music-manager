"""Reproduce FK failure when orphan cleanup deletes SongLayout still referenced by Song.last_song_layout_id."""

import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from abc_music_manager.db.schema import create_schema, seed_defaults, _run_migrations
from abc_music_manager.db.songfile_cleanup import cleanup_orphaned_songs_after_songfile_deletion
from abc_music_manager.parsing.abc_parser import parse_abc_content

ABC = """%%song-title Rride on Me
%%song-composer TestComposer
X:1
T:Part1
K:C
"""


@pytest.fixture
def memory_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    create_schema(conn)
    _run_migrations(conn)
    seed_defaults(conn)
    return conn


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def test_orphan_cleanup_clears_last_song_layout_id(memory_conn: sqlite3.Connection) -> None:
    """Song.last_song_layout_id is cleared before orphan SongLayout rows are deleted."""
    parsed = parse_abc_content(ABC)
    now = _now()
    cur = memory_conn.execute(
        """INSERT INTO Song (title, composers, duration_seconds, transcriber, rating, status_id,
           notes, lyrics, last_played_at, total_plays, parts, created_at, updated_at)
           VALUES (?, ?, NULL, NULL, NULL, 1, NULL, NULL, NULL, 0, '[]', ?, ?)""",
        (parsed.title, parsed.composers, now, now),
    )
    song_id = cur.lastrowid
    memory_conn.execute(
        """INSERT INTO SongFile (song_id, file_path, file_mtime, file_hash, export_timestamp,
           is_primary_library, is_set_copy, scan_excluded, created_at, updated_at)
           VALUES (?, ?, NULL, NULL, NULL, 1, 0, 0, ?, ?)""",
        (song_id, "/Music/Rride on Me.abc", now, now),
    )
    cur = memory_conn.execute(
        """INSERT INTO Band (name, created_at, updated_at) VALUES ('Band', ?, ?)""",
        (now, now),
    )
    band_id = cur.lastrowid
    cur = memory_conn.execute(
        """INSERT INTO BandLayout (band_id, name, created_at, updated_at) VALUES (?, 'Default', ?, ?)""",
        (band_id, now, now),
    )
    bl_id = cur.lastrowid
    cur = memory_conn.execute(
        """INSERT INTO SongLayout (song_id, band_layout_id, name, created_at, updated_at)
           VALUES (?, ?, 'Layout', ?, ?)""",
        (song_id, bl_id, now, now),
    )
    sl_id = cur.lastrowid
    memory_conn.execute(
        """UPDATE Song SET last_band_layout_id = ?, last_song_layout_id = ? WHERE id = ?""",
        (bl_id, sl_id, song_id),
    )
    memory_conn.commit()

    memory_conn.execute("DELETE FROM SongFile WHERE song_id = ?", (song_id,))

    cleanup_orphaned_songs_after_songfile_deletion(memory_conn)

    assert memory_conn.execute("SELECT COUNT(*) FROM Song").fetchone()[0] == 0
    assert memory_conn.execute("SELECT COUNT(*) FROM SongLayout").fetchone()[0] == 0
