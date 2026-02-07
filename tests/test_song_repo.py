"""Unit tests for song repo (logical identity, duplicate detection)."""

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from abc_music_manager.db.schema import create_schema, seed_defaults
from abc_music_manager.db.song_repo import logical_identity, find_song_by_logical_identity
from abc_music_manager.parsing.abc_parser import ParsedSong, PartInfo


def test_logical_identity() -> None:
    parsed = ParsedSong(
        title="  My Title  ",
        composers="Composer A",
        duration_seconds=120,
        transcriber=None,
        export_timestamp=None,
        parts=[PartInfo(1, "P1", "Flute"), PartInfo(2, "P2", None)],
    )
    norm_title, composers, part_count = logical_identity(parsed)
    assert norm_title == "my title"
    assert composers == "Composer A"
    assert part_count == 2


def test_find_song_by_logical_identity_empty() -> None:
    conn = sqlite3.connect(":memory:")
    create_schema(conn)
    seed_defaults(conn)
    ids = find_song_by_logical_identity(conn, "my title", "Composer", 2)
    assert ids == []
    conn.close()


def test_find_song_by_logical_identity_match() -> None:
    conn = sqlite3.connect(":memory:")
    create_schema(conn)
    seed_defaults(conn)
    conn.execute(
        """INSERT INTO Song (title, composers, duration_seconds, transcriber, rating, status_id, notes, lyrics,
           last_played_at, total_plays, parts, created_at, updated_at)
           VALUES (?, ?, ?, ?, NULL, NULL, NULL, NULL, NULL, 0, ?, datetime('now'), datetime('now'))""",
        ("My Title", "Composer A", 120, None, '[{"part_number":1,"part_name":"P1","instrument_id":1},{"part_number":2,"part_name":"P2","instrument_id":null}]'),
    )
    conn.commit()
    ids = find_song_by_logical_identity(conn, "my title", "Composer A", 2)
    assert len(ids) == 1
    conn.close()
