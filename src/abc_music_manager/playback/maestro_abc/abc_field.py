"""
Extended ABC field parsing (%%part-name, %%made-for, etc.).
From AbcField.java.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional


class AbcField(Enum):
    SONG_TITLE = "song-title"
    SONG_COMPOSER = "song-composer"
    SONG_DURATION = "song-duration"
    SONG_TRANSCRIBER = "song-transcriber"
    ABC_VERSION = "abc-version"
    ABC_CREATOR = "abc-creator"
    PART_NAME = "part-name"
    TEMPO = "q:"  # formatted as Q:
    SWING_RHYTHM = "swing-rhythm"
    MIX_TIMINGS = "mix-timings"
    MADE_FOR = "made-for"
    EXPORT_TIMESTAMP = "export-timestamp"
    SKIP_SILENCE_AT_START = "skip-silence-at-start"
    DELETE_MINIMAL_NOTES = "delete-minimal-notes"
    ORGANIC = "organic"
    ORGANIC_MULTI_STAGE = "organic-multi-stage"
    ORGANIC_POLY_6_PLUS = "organic-poly-6-plus"
    USER_PAN = "user-pan"
    REDUCED_FILE_SIZE = "reduced-file-size"
    ORGANIC_VERSION = "organic-version"

    def __init__(self, formatted_name: str) -> None:
        self._formatted_name = formatted_name

    @property
    def formatted_name(self) -> str:
        return self._formatted_name

    @classmethod
    def from_string(cls, s: str) -> Optional["AbcField"]:
        if s.startswith("%%"):
            s = s[2:]
        s = s.strip().rstrip(":")
        if s.lower() == "tempo":
            return cls.TEMPO
        space = s.find(" ")
        if space > 0:
            s = s[:space]
        s_lower = s.lower()
        for f in cls:
            if f.formatted_name.lower() == s_lower:
                return f
        return None
