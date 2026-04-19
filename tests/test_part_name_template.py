"""Part renaming template and ABC T: rewriter tests."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from abc_music_manager.services.abc_part_title_rewrite import (
    rewrite_abc_part_t_lines,
    sanitize_t_title_value,
)
from abc_music_manager.services.filename_template import (
    compute_part_numeration,
    format_part_name,
)


def test_compute_part_numeration_unique() -> None:
    parts = [
        {"part_number": 1, "part_name": "A"},
        {"part_number": 2, "part_name": "B"},
    ]
    n = compute_part_numeration(parts)
    assert n[1] == ""
    assert n[2] == ""


def test_compute_part_numeration_duplicates() -> None:
    parts = [
        {"part_number": 1, "part_name": "Basic Flute"},
        {"part_number": 2, "part_name": "Basic Flute"},
    ]
    n = compute_part_numeration(parts)
    assert n[1] == "1"
    assert n[2] == "2"


def test_format_part_name_variables() -> None:
    s = format_part_name(
        "$PartTitle - $PartName ($PartNumber) [$PlayerAssignment] $Numeration",
        file_path=r"C:\m\file.abc",
        index=0,
        title="Song",
        composers="C",
        transcriber=None,
        duration_seconds=60,
        part_count=2,
        part_instrument="Lute",
        part_name="pn",
        part_title="pt",
        part_number_display="3",
        player_assignment="P",
        numeration="2",
        whitespace_replace=" ",
        part_count_zero_padded=True,
    )
    assert "pt" in s and "pn" in s and "3" in s and "P" in s and "2" in s


def test_rewrite_replace_first_t() -> None:
    abc = "X:1\nT:Old\n%%part-name Flute\nK:C\n"
    out = rewrite_abc_part_t_lines(abc, {1: "New Title"})
    assert "T: New Title" in out
    assert "T:Old" not in out
    assert "%%part-name Flute" in out


def test_rewrite_insert_t_when_missing() -> None:
    abc = "X:1\n%%part-name Flute\nK:C\n"
    out = rewrite_abc_part_t_lines(abc, {1: "Inserted"})
    assert "T: Inserted" in out


def test_rewrite_second_part_block() -> None:
    abc = "X:1\nT:A\nX:2\nT:B\n"
    out = rewrite_abc_part_t_lines(abc, {2: "Second"})
    assert "T:A" in out
    assert "T: Second" in out
    assert "T:B" not in out


def test_sanitize_t_title_strips_newlines() -> None:
    assert sanitize_t_title_value("a\nb") == "a b"
