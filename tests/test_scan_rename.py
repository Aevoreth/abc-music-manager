"""Scan after file rename with title fix should not FK-fail or duplicate songs."""

import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from abc_music_manager.db.schema import create_schema, seed_defaults, _run_migrations
from abc_music_manager.scanning.scanner import run_scan

ABC_OLD = """%%song-title Rride on Me
%%song-composer TestComposer
X:1
T:Part1
K:C
"""

ABC_NEW = """%%song-title Ride on Me
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


def test_rescan_after_rename_and_title_fix(tmp_path: Path, memory_conn: sqlite3.Connection) -> None:
    music = tmp_path / "Music"
    music.mkdir()
    old_path = music / "Rride on Me.abc"
    new_path = music / "Ride on Me.abc"
    old_path.write_text(ABC_OLD, encoding="utf-8")

    def fake_roots(_conn: sqlite3.Connection):
        return ([str(music.resolve())], [], [])

    with patch("abc_music_manager.scanning.scanner.get_enabled_roots", side_effect=fake_roots):
        run_scan(memory_conn)

    song_id = memory_conn.execute("SELECT song_id FROM SongFile").fetchone()[0]
    now = _now()
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

    old_path.unlink()
    new_path.write_text(ABC_NEW, encoding="utf-8")

    with patch("abc_music_manager.scanning.scanner.get_enabled_roots", side_effect=fake_roots):
        run_scan(memory_conn)

    assert memory_conn.execute("SELECT COUNT(*) FROM Song").fetchone()[0] == 1
    assert memory_conn.execute("SELECT COUNT(*) FROM SongFile").fetchone()[0] == 1
    row = memory_conn.execute("SELECT file_path FROM SongFile").fetchone()
    assert row is not None and row[0].endswith("Ride on Me.abc")
    title = memory_conn.execute("SELECT title FROM Song").fetchone()[0]
    assert title == "Ride on Me"
    assert memory_conn.execute("SELECT last_song_layout_id FROM Song").fetchone()[0] is not None
