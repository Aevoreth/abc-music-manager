"""CSV part sheet applies optional find/replace rules to part cells."""

import csv
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from abc_music_manager.db.schema import init_database
from abc_music_manager.services.set_export_service import (
    SetExportSettings,
    apply_csv_part_display_renames,
    export_set,
)


def test_apply_csv_part_display_renames_order_and_literal() -> None:
    rules = [("Basic Theorbo", "Theorbo"), ("Misty Mountain Harp", "MMH")]
    assert apply_csv_part_display_renames("Basic Theorbo / Misty Mountain Harp", rules) == "Theorbo / MMH"


def test_export_csv_part_rename_rules() -> None:
    base = tempfile.mkdtemp()
    db_path = Path(base) / "test.db"
    conn = init_database(db_path)
    try:
        src = Path(base) / "src"
        src.mkdir()
        a_path = src / "a.abc"
        a_path.write_text("X:1\nT:test\n", encoding="utf-8")

        out_parent = Path(base) / "out"
        out_parent.mkdir()

        now = "2020-01-01T00:00:00+00:00"
        parts = (
            '[{"part_number":1,"part_name":"Misty Mountain Harp","instrument_id":null},'
            '{"part_number":2,"part_name":"Basic Theorbo","instrument_id":null}]'
        )
        conn.execute(
            """INSERT INTO Song (title, composers, duration_seconds, transcriber, rating, status_id, notes, lyrics,
               last_played_at, total_plays, parts, created_at, updated_at)
               VALUES (?, ?, ?, ?, NULL, 1, NULL, NULL, NULL, 0, ?, ?, ?)""",
            ("A", "C", 60, None, parts, now, now),
        )
        sid = conn.execute("SELECT id FROM Song WHERE title = 'A'").fetchone()[0]
        conn.execute(
            """INSERT INTO SongFile (song_id, file_path, file_mtime, file_hash, export_timestamp,
               is_primary_library, is_set_copy, scan_excluded, created_at, updated_at)
               VALUES (?, ?, NULL, NULL, NULL, 1, 0, 0, ?, ?)""",
            (sid, str(a_path), now, now),
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
            (sl_id, sid, 0, now, now),
        )
        conn.commit()

        settings = SetExportSettings(
            output_directory=out_parent,
            set_name="MySet",
            export_as_folder=True,
            export_as_zip=False,
            rename_abc_files=False,
            filename_pattern="$SongIndex_$FileName",
            whitespace_replace=" ",
            part_count_zero_padded=True,
            export_csv_part_sheet=True,
            export_abcp_playlist=False,
            include_composer_in_csv=False,
            csv_use_visible_columns=True,
            csv_columns_enabled={},
            csv_part_columns="part",
            rename_parts=False,
            part_name_pattern="$PartTitle",
            csv_part_rename_rules=[("Misty Mountain Harp", "MMH"), ("Basic Theorbo", "Theorbo")],
        )
        export_set(conn, sl_id, "Test Set", None, settings, None, status_callback=None)

        csv_path = out_parent / "MySet" / "MySet.csv"
        assert csv_path.is_file()
        with open(csv_path, newline="", encoding="utf-8") as f:
            rows = list(csv.reader(f))
        assert len(rows) == 2
        # Title, Parts, Duration, Artist — Part 1, Part 2
        assert rows[0][-2:] == ["Part 1", "Part 2"]
        assert rows[1][-2:] == ["MMH", "Theorbo"]
    finally:
        conn.close()
        shutil.rmtree(base, ignore_errors=True)
