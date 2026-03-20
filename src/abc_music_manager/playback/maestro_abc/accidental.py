"""
Accidental: sharp, flat, natural for key signatures.
From Accidental.java.
"""

from __future__ import annotations

from enum import Enum


class Accidental(Enum):
    NONE = ("", 0)
    DOUBLE_FLAT = ("__", -2)
    FLAT = ("_", -1)
    NATURAL = ("=", 0)
    SHARP = ("^", 1)
    DOUBLE_SHARP = ("^^", 2)

    def __init__(self, abc: str, delta_note_id: int) -> None:
        self.abc = abc
        self.delta_note_id = delta_note_id

    def __str__(self) -> str:
        return self.abc

    @classmethod
    def from_delta_id(cls, delta_note_id: int) -> "Accidental":
        mapping = {
            -2: cls.DOUBLE_FLAT,
            -1: cls.FLAT,
            0: cls.NATURAL,
            1: cls.SHARP,
            2: cls.DOUBLE_SHARP,
        }
        return mapping.get(delta_note_id, cls.NONE)
