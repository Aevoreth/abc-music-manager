"""Scanner duplicate handling with batch resolution callback and temp library files."""

import sqlite3
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from abc_music_manager.db.schema import create_schema, seed_defaults, _run_migrations
from abc_music_manager.scanning.duplicate_types import DuplicateCandidate, DuplicateDecision
from abc_music_manager.scanning.scanner import run_scan

ABC_FIRST = """%%song-title BatchDup
%%song-composer TestComposer
X:1
"""

ABC_SECOND = """%%song-title BatchDup
%%song-composer TestComposer
X:1
%%%second-file-marker
"""


@pytest.fixture
def memory_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    create_schema(conn)
    _run_migrations(conn)
    seed_defaults(conn)
    return conn


def test_batch_separate_creates_two_songs(tmp_path: Path, memory_conn: sqlite3.Connection) -> None:
    music = tmp_path / "Music"
    music.mkdir()
    (music / "a.abc").write_text(ABC_FIRST, encoding="utf-8")
    (music / "b.abc").write_text(ABC_SECOND, encoding="utf-8")

    def fake_roots(_conn: sqlite3.Connection):
        return ([str(music.resolve())], [], [])

    def batch(_conn: sqlite3.Connection, pending: list[DuplicateCandidate]):
        return [DuplicateDecision(c.new_path, "separate", None) for c in pending]

    with patch("abc_music_manager.scanning.scanner.get_enabled_roots", side_effect=fake_roots):
        total, scanned, errors = run_scan(memory_conn, on_duplicates_batch=batch)

    assert total == 2
    assert errors == 0
    assert memory_conn.execute("SELECT COUNT(*) FROM Song").fetchone()[0] == 2
    assert memory_conn.execute("SELECT COUNT(*) FROM SongFile").fetchone()[0] == 2
    memory_conn.close()


def test_batch_keep_existing_leaves_one_song(tmp_path: Path, memory_conn: sqlite3.Connection) -> None:
    music = tmp_path / "Music"
    music.mkdir()
    (music / "a.abc").write_text(ABC_FIRST, encoding="utf-8")
    (music / "b.abc").write_text(ABC_SECOND, encoding="utf-8")

    def fake_roots(_conn: sqlite3.Connection):
        return ([str(music.resolve())], [], [])

    def batch(_conn: sqlite3.Connection, pending: list[DuplicateCandidate]):
        assert len(pending) == 1
        sid = pending[0].existing_song_ids[0]
        return [DuplicateDecision(pending[0].new_path, "keep_existing", sid)]

    with patch("abc_music_manager.scanning.scanner.get_enabled_roots", side_effect=fake_roots):
        run_scan(memory_conn, on_duplicates_batch=batch)

    assert memory_conn.execute("SELECT COUNT(*) FROM Song").fetchone()[0] == 1
    assert memory_conn.execute("SELECT COUNT(*) FROM SongFile").fetchone()[0] == 1
    row = memory_conn.execute("SELECT file_path FROM SongFile").fetchone()
    assert row is not None and str(row[0]).endswith("a.abc")
    memory_conn.close()


def test_batch_cancel_ignores_new_files(tmp_path: Path, memory_conn: sqlite3.Connection) -> None:
    music = tmp_path / "Music"
    music.mkdir()
    (music / "a.abc").write_text(ABC_FIRST, encoding="utf-8")
    (music / "b.abc").write_text(ABC_SECOND, encoding="utf-8")

    def fake_roots(_conn: sqlite3.Connection):
        return ([str(music.resolve())], [], [])

    def batch(_conn: sqlite3.Connection, _pending: list[DuplicateCandidate]):
        return None

    with patch("abc_music_manager.scanning.scanner.get_enabled_roots", side_effect=fake_roots):
        run_scan(memory_conn, on_duplicates_batch=batch)

    assert memory_conn.execute("SELECT COUNT(*) FROM Song").fetchone()[0] == 1
    assert memory_conn.execute("SELECT COUNT(*) FROM SongFile").fetchone()[0] == 1
    memory_conn.close()
