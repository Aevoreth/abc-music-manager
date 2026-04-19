"""Set export writes an ABCP playlist with paths relative to the exported ABC files."""

import shutil
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from abc_music_manager.db.schema import init_database
from abc_music_manager.services.abcp_service import parse_abcp
from abc_music_manager.services.set_export_service import SetExportSettings, export_set


@pytest.mark.parametrize("export_abcp_playlist,expect_file", [(True, True), (False, False)])
def test_set_export_abcp_playlist_optional(export_abcp_playlist: bool, expect_file: bool) -> None:
    base = tempfile.mkdtemp()
    db_path = Path(base) / "test.db"
    conn = init_database(db_path)
    try:
        src = Path(base) / "src"
        src.mkdir()
        a_path = src / "a.abc"
        b_path = src / "b.abc"
        a_path.write_text("X:1\nT:test\n", encoding="utf-8")
        b_path.write_text("X:1\nT:test2\n", encoding="utf-8")

        out_parent = Path(base) / "out"
        out_parent.mkdir()

        now = "2020-01-01T00:00:00+00:00"
        parts = '[{"part_number":1,"part_name":"P1","instrument_id":null}]'
        conn.execute(
            """INSERT INTO Song (title, composers, duration_seconds, transcriber, rating, status_id, notes, lyrics,
               last_played_at, total_plays, parts, created_at, updated_at)
               VALUES (?, ?, ?, ?, NULL, 1, NULL, NULL, NULL, 0, ?, ?, ?)""",
            ("A", "C", 60, None, parts, now, now),
        )
        conn.execute(
            """INSERT INTO Song (title, composers, duration_seconds, transcriber, rating, status_id, notes, lyrics,
               last_played_at, total_plays, parts, created_at, updated_at)
               VALUES (?, ?, ?, ?, NULL, 1, NULL, NULL, NULL, 0, ?, ?, ?)""",
            ("B", "C", 60, None, parts, now, now),
        )
        sid1 = conn.execute("SELECT id FROM Song WHERE title = 'A'").fetchone()[0]
        sid2 = conn.execute("SELECT id FROM Song WHERE title = 'B'").fetchone()[0]
        conn.execute(
            """INSERT INTO SongFile (song_id, file_path, file_mtime, file_hash, export_timestamp,
               is_primary_library, is_set_copy, scan_excluded, created_at, updated_at)
               VALUES (?, ?, NULL, NULL, NULL, 1, 0, 0, ?, ?)""",
            (sid1, str(a_path), now, now),
        )
        conn.execute(
            """INSERT INTO SongFile (song_id, file_path, file_mtime, file_hash, export_timestamp,
               is_primary_library, is_set_copy, scan_excluded, created_at, updated_at)
               VALUES (?, ?, NULL, NULL, NULL, 1, 0, 0, ?, ?)""",
            (sid2, str(b_path), now, now),
        )
        conn.execute(
            """INSERT INTO Setlist (name, band_layout_id, folder_id, sort_order, locked, notes, created_at, updated_at)
               VALUES (?, NULL, NULL, 0, 0, NULL, ?, ?)""",
            ("Test Set", now, now),
        )
        sl_id = conn.execute("SELECT id FROM Setlist WHERE name = 'Test Set'").fetchone()[0]
        conn.execute(
            """INSERT INTO SetlistItem (setlist_id, song_id, position, override_change_duration_seconds,
               song_layout_id, created_at, updated_at)
               VALUES (?, ?, ?, NULL, NULL, ?, ?)""",
            (sl_id, sid1, 0, now, now),
        )
        conn.execute(
            """INSERT INTO SetlistItem (setlist_id, song_id, position, override_change_duration_seconds,
               song_layout_id, created_at, updated_at)
               VALUES (?, ?, ?, NULL, NULL, ?, ?)""",
            (sl_id, sid2, 1, now, now),
        )
        conn.commit()

        settings = SetExportSettings(
            output_directory=out_parent,
            set_name="MySet",
            export_as_folder=True,
            export_as_zip=False,
            rename_abc_files=True,
            filename_pattern="$SongIndex_$FileName",
            whitespace_replace="_",
            part_count_zero_padded=True,
            export_csv_part_sheet=False,
            export_abcp_playlist=export_abcp_playlist,
            include_composer_in_csv=True,
            csv_use_visible_columns=True,
            csv_columns_enabled={},
            csv_part_columns="part",
            rename_parts=False,
            part_name_pattern="$PartTitle",
            csv_part_rename_rules=[],
        )
        export_set(conn, sl_id, "Test Set", None, settings, None, status_callback=None)

        folder = out_parent / "MySet"
        abcp = folder / "MySet.abcp"
        assert (folder / "001_a.abc").is_file()
        assert (folder / "002_b.abc").is_file()
        if expect_file:
            assert abcp.is_file()
            assert parse_abcp(abcp) == ["001_a.abc", "002_b.abc"]
        else:
            assert not abcp.exists()
    finally:
        conn.close()
        shutil.rmtree(base, ignore_errors=True)
