"""Duplicate folder structure detection and apply (library only)."""

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from abc_music_manager.db.schema import create_schema, seed_defaults, _run_migrations
from abc_music_manager.db.song_repo import ensure_song_from_parsed
from abc_music_manager.scanning.folder_duplicate_apply import (
    FolderClusterApply,
    apply_folder_cluster_resolutions,
    path_is_under_any_root,
)
from abc_music_manager.scanning.folder_duplicate_detect import detect_duplicate_folder_clusters

ABC_BODY = """%%song-title DupTune
%%song-composer SamePerson
X:1
"""


@pytest.fixture
def memory_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    create_schema(conn)
    _run_migrations(conn)
    seed_defaults(conn)
    return conn


def test_detect_finds_mirror_folders(tmp_path: Path) -> None:
    music = tmp_path / "Music"
    (music / "CopyA" / "sub").mkdir(parents=True)
    (music / "CopyB" / "sub").mkdir(parents=True)
    (music / "CopyA" / "sub" / "x.abc").write_text(ABC_BODY, encoding="utf-8")
    (music / "CopyB" / "sub" / "x.abc").write_text(ABC_BODY, encoding="utf-8")

    clusters = detect_duplicate_folder_clusters(
        [str(music.resolve())],
        [],
        [],
    )

    assert len(clusters) >= 1
    roots = set(clusters[0].root_paths)
    assert any("CopyA" in r for r in roots)
    assert any("CopyB" in r for r in roots)


def test_detect_no_match_when_extra_file(tmp_path: Path) -> None:
    music = tmp_path / "Music"
    (music / "CopyA" / "sub").mkdir(parents=True)
    (music / "CopyB" / "sub").mkdir(parents=True)
    (music / "CopyA" / "sub" / "x.abc").write_text(ABC_BODY, encoding="utf-8")
    (music / "CopyB" / "sub" / "x.abc").write_text(ABC_BODY, encoding="utf-8")
    (music / "CopyB" / "sub" / "y.abc").write_text(ABC_BODY, encoding="utf-8")

    clusters = detect_duplicate_folder_clusters(
        [str(music.resolve())],
        [],
        [],
    )
    def cluster_has_both_ab(c) -> bool:
        rs = c.root_paths
        return any("CopyA" in r for r in rs) and any("CopyB" in r for r in rs)

    assert not any(cluster_has_both_ab(c) for c in clusters)


def test_path_is_under_any_root(tmp_path: Path) -> None:
    root = tmp_path / "lose"
    root.mkdir()
    child = root / "deep" / "b.abc"
    child.parent.mkdir(parents=True)
    child.write_text("x", encoding="utf-8")
    rset = {str(root.resolve())}
    assert path_is_under_any_root(str(child.resolve()), rset) is True
    assert path_is_under_any_root(str(tmp_path / "other.abc"), rset) is False


def test_unindex_removes_songfiles(memory_conn: sqlite3.Connection, tmp_path: Path) -> None:
    from abc_music_manager.parsing.abc_parser import parse_abc_file

    lose = tmp_path / "Lose"
    lose.mkdir()
    f = lose / "t.abc"
    f.write_text(ABC_BODY, encoding="utf-8")
    fp = str(f.resolve())
    ensure_song_from_parsed(memory_conn, parse_abc_file(f), fp)

    before = memory_conn.execute("SELECT COUNT(*) FROM SongFile").fetchone()[0]
    assert before == 1

    keep = tmp_path / "Keep"
    keep.mkdir()
    apply_folder_cluster_resolutions(
        memory_conn,
        [FolderClusterApply(keep_root=str(keep.resolve()), losers=[(str(lose.resolve()), "unindex")])],
    )
    after = memory_conn.execute("SELECT COUNT(*) FROM SongFile").fetchone()[0]
    assert after == 0
    memory_conn.close()
