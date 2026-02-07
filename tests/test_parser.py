"""Unit tests for ABC parser (Maestro tags, fallbacks, parts)."""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from abc_music_manager.parsing.abc_parser import (
    parse_abc_content,
    ParsedSong,
    PartInfo,
)


def test_maestro_title_composer_duration() -> None:
    content = """
%%song-title       My Song
%%song-composer    The Composer
%%song-duration    3:45
%%song-transcriber Someone
X: 1
T: Ignored
"""
    parsed = parse_abc_content(content)
    assert parsed.title == "My Song"
    assert parsed.composers == "The Composer"
    assert parsed.duration_seconds == 3 * 60 + 45
    assert parsed.transcriber == "Someone"


def test_fallback_t_c_filename() -> None:
    content = """
T: Fallback Title
C: Fallback Composer
X: 1
"""
    parsed = parse_abc_content(content, filename="myfile.abc")
    assert parsed.title == "Fallback Title"
    assert parsed.composers == "Fallback Composer"


def test_fallback_filename_when_no_t() -> None:
    parsed = parse_abc_content("X: 1\n", filename="only_filename.abc")
    assert parsed.title == "only_filename.abc"


def test_parts_count_and_made_for() -> None:
    content = """
%%song-title Test
%%song-composer A
X: 1
%%part-name Part One
%%made-for Flute
X: 2
%%part-name Part Two
%%made-for Lute
"""
    parsed = parse_abc_content(content)
    assert len(parsed.parts) == 2
    assert parsed.parts[0].part_number == 1
    assert parsed.parts[0].part_name == "Part One"
    assert parsed.parts[0].made_for == "Flute"
    assert parsed.parts[1].part_number == 2
    assert parsed.parts[1].part_name == "Part Two"
    assert parsed.parts[1].made_for == "Lute"


def test_mm_ss_parsing() -> None:
    content = "%%song-title x\n%%song-composer y\n%%song-duration 1:30\nX: 1\n"
    parsed = parse_abc_content(content)
    assert parsed.duration_seconds == 90
