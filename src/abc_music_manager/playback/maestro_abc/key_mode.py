"""
Key mode: major, minor, dorian, etc.
From KeyMode.java.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional


class KeyMode(Enum):
    MAJOR = "MAJ"
    MINOR = "MIN"
    DORIAN = "DOR"
    PHRYGIAN = "PHR"
    LYDIAN = "LYD"
    MIXOLYDIAN = "MIX"
    AEOLIAN = "AEO"
    IONIAN = "ION"
    LOCRIAN = "LOC"

    def __init__(self, short: str) -> None:
        self._short = short

    @property
    def short_string(self) -> str:
        return self._short

    @classmethod
    def parse_mode(cls, mode_string: str) -> Optional["KeyMode"]:
        if not mode_string or mode_string == "M":
            return cls.MAJOR
        if mode_string == "m":
            return cls.MINOR
        if len(mode_string) > 3:
            mode_string = mode_string[:3]
        mode_string = mode_string.upper()
        for mode in cls:
            if mode.short_string == mode_string:
                return mode
        return None
