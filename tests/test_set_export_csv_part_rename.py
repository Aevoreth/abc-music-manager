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


def test_export_csv_player_instruments_summary_with_band_layout() -> None:
    """After the part grid, CSV includes blank rows and a player → unique instruments table."""
    base = tempfile.mkdtemp()
    db_path = Path(base) / "test.db"
    conn = init_database(db_path)
    try:
        theorbo_id = conn.execute(
            "SELECT id FROM Instrument WHERE name = ?", ("Basic Theorbo",)
        ).fetchone()[0]
        flute_id = conn.execute(
            "SELECT id FROM Instrument WHERE name = ?", ("Basic Flute",)
        ).fetchone()[0]
        harp_id = conn.execute(
            "SELECT id FROM Instrument WHERE name = ?", ("Basic Harp",)
        ).fetchone()[0]

        now = "2020-01-01T00:00:00+00:00"
        conn.execute(
            "INSERT INTO Band (name, created_at, updated_at) VALUES (?, ?, ?)",
            ("T", now, now),
        )
        band_id = conn.execute("SELECT id FROM Band WHERE name = 'T'").fetchone()[0]
        conn.execute(
            """INSERT INTO BandLayout (band_id, name, created_at, updated_at)
               VALUES (?, ?, ?, ?)""",
            (band_id, "L1", now, now),
        )
        layout_id = conn.execute("SELECT id FROM BandLayout WHERE name = 'L1'").fetchone()[0]
        conn.execute(
            "INSERT INTO Player (name, created_at, updated_at) VALUES (?, ?, ?)",
            ("Alice", now, now),
        )
        conn.execute(
            "INSERT INTO Player (name, created_at, updated_at) VALUES (?, ?, ?)",
            ("Bob", now, now),
        )
        alice_id = conn.execute("SELECT id FROM Player WHERE name = 'Alice'").fetchone()[0]
        bob_id = conn.execute("SELECT id FROM Player WHERE name = 'Bob'").fetchone()[0]
        conn.execute(
            """INSERT INTO BandLayoutSlot (band_layout_id, player_id, x, y, width_units, height_units, created_at, updated_at)
               VALUES (?, ?, 0, 0, 7, 5, ?, ?), (?, ?, 1, 0, 7, 5, ?, ?)""",
            (layout_id, alice_id, now, now, layout_id, bob_id, now, now),
        )

        src = Path(base) / "src"
        src.mkdir()
        a_path = src / "a.abc"
        b_path = src / "b.abc"
        a_path.write_text("X:1\nT:a\n", encoding="utf-8")
        b_path.write_text("X:1\nT:b\n", encoding="utf-8")

        parts1 = (
            f'[{{"part_number":1,"part_name":"A1","instrument_id":{theorbo_id}}},'
            f'{{"part_number":2,"part_name":"B1","instrument_id":{flute_id}}}]'
        )
        parts2 = (
            f'[{{"part_number":1,"part_name":"A2","instrument_id":{theorbo_id}}},'
            f'{{"part_number":2,"part_name":"B2","instrument_id":{harp_id}}}]'
        )
        conn.execute(
            """INSERT INTO Song (title, composers, duration_seconds, transcriber, rating, status_id, notes, lyrics,
               last_played_at, total_plays, parts, created_at, updated_at)
               VALUES (?, ?, ?, ?, NULL, 1, NULL, NULL, NULL, 0, ?, ?, ?)""",
            ("S1", "C", 60, None, parts1, now, now),
        )
        conn.execute(
            """INSERT INTO Song (title, composers, duration_seconds, transcriber, rating, status_id, notes, lyrics,
               last_played_at, total_plays, parts, created_at, updated_at)
               VALUES (?, ?, ?, ?, NULL, 1, NULL, NULL, NULL, 0, ?, ?, ?)""",
            ("S2", "C", 60, None, parts2, now, now),
        )
        sid1 = conn.execute("SELECT id FROM Song WHERE title = 'S1'").fetchone()[0]
        sid2 = conn.execute("SELECT id FROM Song WHERE title = 'S2'").fetchone()[0]
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
               VALUES (?, ?, NULL, 0, 0, NULL, ?, ?)""",
            ("Gig", layout_id, now, now),
        )
        sl_id = conn.execute("SELECT id FROM Setlist WHERE name = 'Gig'").fetchone()[0]
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
        item1 = conn.execute(
            "SELECT id FROM SetlistItem WHERE setlist_id = ? AND song_id = ?", (sl_id, sid1)
        ).fetchone()[0]
        item2 = conn.execute(
            "SELECT id FROM SetlistItem WHERE setlist_id = ? AND song_id = ?", (sl_id, sid2)
        ).fetchone()[0]
        for item_id, pid, pn in (
            (item1, alice_id, 1),
            (item1, bob_id, 2),
            (item2, alice_id, 1),
            (item2, bob_id, 2),
        ):
            conn.execute(
                """INSERT INTO SetlistBandAssignment (setlist_item_id, player_id, part_number, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (item_id, pid, pn, now, now),
            )
        conn.commit()

        out_parent = Path(base) / "out"
        out_parent.mkdir()
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
            csv_part_columns="instrument",
            rename_parts=False,
            part_name_pattern="$PartTitle",
            csv_part_rename_rules=[],
        )
        export_set(conn, sl_id, "Gig", layout_id, settings, [alice_id, bob_id], status_callback=None)

        csv_path = out_parent / "MySet" / "MySet.csv"
        with open(csv_path, newline="", encoding="utf-8") as f:
            rows = list(csv.reader(f))

        header = rows[0]
        assert header[-2:] == ["Alice", "Bob"]
        assert len(rows) == 1 + 2 + 3 + 1 + 2  # header + 2 songs + 3 blanks + summary header + 2 players

        blank = [""] * len(header)
        assert rows[3:6] == [blank, blank, blank]
        assert rows[6] == ["Player Name", "Instruments needed"]

        summary = {rows[7][0]: rows[7][1], rows[8][0]: rows[8][1]}
        assert summary["Alice"] == "Basic Theorbo"
        assert set(summary["Bob"].split(", ")) == {"Basic Flute", "Basic Harp"}
    finally:
        conn.close()
        shutil.rmtree(base, ignore_errors=True)


def test_csv_appendix_uses_made_for_catalog_name_not_part_names_or_renames() -> None:
    """Appendix lists %%made-for (instrument_id) catalog names only; ignores part names and CSV renames."""
    base = tempfile.mkdtemp()
    db_path = Path(base) / "test.db"
    conn = init_database(db_path)
    try:
        theorbo_id = conn.execute(
            "SELECT id FROM Instrument WHERE name = ?", ("Basic Theorbo",)
        ).fetchone()[0]
        now = "2020-01-01T00:00:00+00:00"
        conn.execute(
            "INSERT INTO Band (name, created_at, updated_at) VALUES (?, ?, ?)",
            ("T", now, now),
        )
        band_id = conn.execute("SELECT id FROM Band WHERE name = 'T'").fetchone()[0]
        conn.execute(
            """INSERT INTO BandLayout (band_id, name, created_at, updated_at)
               VALUES (?, ?, ?, ?)""",
            (band_id, "L1", now, now),
        )
        layout_id = conn.execute("SELECT id FROM BandLayout WHERE name = 'L1'").fetchone()[0]
        conn.execute(
            "INSERT INTO Player (name, created_at, updated_at) VALUES (?, ?, ?)",
            ("Alice", now, now),
        )
        alice_id = conn.execute("SELECT id FROM Player WHERE name = 'Alice'").fetchone()[0]
        conn.execute(
            """INSERT INTO BandLayoutSlot (band_layout_id, player_id, x, y, width_units, height_units, created_at, updated_at)
               VALUES (?, ?, 0, 0, 7, 5, ?, ?)""",
            (layout_id, alice_id, now, now),
        )

        src = Path(base) / "src"
        src.mkdir()
        a_path = src / "a.abc"
        a_path.write_text("X:1\nT:a\n", encoding="utf-8")

        parts = (
            f'[{{"part_number":1,"part_name":"Long Part Label","instrument_id":{theorbo_id},'
            f'"title_from_t":"t"}}]'
        )
        conn.execute(
            """INSERT INTO Song (title, composers, duration_seconds, transcriber, rating, status_id, notes, lyrics,
               last_played_at, total_plays, parts, created_at, updated_at)
               VALUES (?, ?, ?, ?, NULL, 1, NULL, NULL, NULL, 0, ?, ?, ?)""",
            ("S1", "C", 60, None, parts, now, now),
        )
        sid = conn.execute("SELECT id FROM Song WHERE title = 'S1'").fetchone()[0]
        conn.execute(
            """INSERT INTO SongFile (song_id, file_path, file_mtime, file_hash, export_timestamp,
               is_primary_library, is_set_copy, scan_excluded, created_at, updated_at)
               VALUES (?, ?, NULL, NULL, NULL, 1, 0, 0, ?, ?)""",
            (sid, str(a_path), now, now),
        )
        conn.execute(
            """INSERT INTO Setlist (name, band_layout_id, folder_id, sort_order, locked, notes, created_at, updated_at)
               VALUES (?, ?, NULL, 0, 0, NULL, ?, ?)""",
            ("Gig", layout_id, now, now),
        )
        sl_id = conn.execute("SELECT id FROM Setlist WHERE name = 'Gig'").fetchone()[0]
        conn.execute(
            """INSERT INTO SetlistItem (setlist_id, song_id, position, override_change_duration_seconds,
               song_layout_id, created_at, updated_at)
               VALUES (?, ?, ?, NULL, NULL, ?, ?)""",
            (sl_id, sid, 0, now, now),
        )
        item_id = conn.execute(
            "SELECT id FROM SetlistItem WHERE setlist_id = ? AND song_id = ?", (sl_id, sid)
        ).fetchone()[0]
        conn.execute(
            """INSERT INTO SetlistBandAssignment (setlist_item_id, player_id, part_number, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?)""",
            (item_id, alice_id, 1, now, now),
        )
        conn.commit()

        out_parent = Path(base) / "out"
        out_parent.mkdir()
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
            csv_part_rename_rules=[("Long Part Label", "Short"), ("Basic Theorbo", "TBO")],
        )
        export_set(conn, sl_id, "Gig", layout_id, settings, [alice_id], status_callback=None)

        with open(out_parent / "MySet" / "MySet.csv", newline="", encoding="utf-8") as f:
            rows = list(csv.reader(f))

        assert rows[1][-1] == "1: Short"
        # header + 1 data + 3 blanks + summary header + 1 player row => summary at index 6
        summary = {rows[6][0]: rows[6][1]}
        assert summary["Alice"] == "Basic Theorbo"
    finally:
        conn.close()
        shutil.rmtree(base, ignore_errors=True)
