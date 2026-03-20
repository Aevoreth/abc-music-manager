"""
Key signature: key parsing, getDefaultAccidental for key signature lookup.
From KeySignature.java.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .accidental import Accidental
from .key_mode import KeyMode

# CX.id = 0, so chroma = id % 12 for notes. White keys: C=0, D=2, E=4, F=5, G=7, A=9, B=11
# Order of sharps: F C G D A E B -> chroma 5, 0, 7, 2, 9, 4, 11
SHARPS_CHROMA = [5, 0, 7, 2, 9, 4, 11]
# Order of flats: B E A D G C F -> chroma 11, 4, 9, 2, 7, 0, 5
FLATS_CHROMA = [11, 4, 9, 2, 7, 0, 5]

MAJOR_KEYS = [
    "Cb", "Gb", "Db", "Ab", "Eb", "Bb", "F",
    "C",
    "G", "D", "A", "E", "B", "F#", "C#",
]
MINOR_KEYS = [
    "Ab", "Eb", "Bb", "F", "C", "G", "D",
    "A",
    "E", "B", "F#", "C#", "G#", "D#", "A#",
]
DORIAN_KEYS = [
    "Db", "Ab", "Eb", "Bb", "F", "C", "G",
    "D",
    "A", "E", "B", "F#", "C#", "G#", "D#",
]
PHRYGIAN_KEYS = [
    "Eb", "Bb", "F", "C", "G", "D", "A",
    "E",
    "B", "F#", "C#", "G#", "D#", "A#", "E#",
]
LYDIAN_KEYS = [
    "Fb", "Cb", "Gb", "Db", "Ab", "Eb", "Bb",
    "F",
    "C", "G", "D", "A", "E", "B", "F#",
]
MIXOLYDIAN_KEYS = [
    "Gb", "Db", "Ab", "Eb", "Bb", "F", "C",
    "G",
    "D", "A", "E", "B", "F#", "C#", "G#",
]
LOCRIAN_KEYS = [
    "Bb", "F", "C", "G", "D", "A", "E",
    "B",
    "F#", "C#", "G#", "D#", "A#", "E#", "B#",
]


def _mode_to_keys(mode: KeyMode) -> Optional[list[str]]:
    mapping = {
        KeyMode.MAJOR: MAJOR_KEYS,
        KeyMode.IONIAN: MAJOR_KEYS,
        KeyMode.MINOR: MINOR_KEYS,
        KeyMode.AEOLIAN: MINOR_KEYS,
        KeyMode.DORIAN: DORIAN_KEYS,
        KeyMode.PHRYGIAN: PHRYGIAN_KEYS,
        KeyMode.LYDIAN: LYDIAN_KEYS,
        KeyMode.MIXOLYDIAN: MIXOLYDIAN_KEYS,
        KeyMode.LOCRIAN: LOCRIAN_KEYS,
    }
    return mapping.get(mode)


@dataclass(frozen=True)
class KeySignature:
    """Key signature: sharps/flats (-7 to 7) and mode."""

    sharps_flats: int
    mode: KeyMode

    def __post_init__(self) -> None:
        if not -7 <= self.sharps_flats <= 7:
            raise ValueError("Key signatures can't have more than 7 sharps or flats")

    def get_default_accidental(self, natural_id: int) -> Accidental:
        """Default accidental for a white-key note in this key."""
        # naturalId is the MIDI id of the natural (C, D, E, etc.)
        chroma = (natural_id - 0) % 12  # CX.id = 0
        if self.sharps_flats > 0:
            for i in range(self.sharps_flats):
                if SHARPS_CHROMA[i] == chroma:
                    return Accidental.SHARP
        elif self.sharps_flats < 0:
            for i in range(-self.sharps_flats):
                if FLATS_CHROMA[i] == chroma:
                    return Accidental.FLAT
        return Accidental.NONE

    @classmethod
    def from_string(cls, s: str) -> "KeySignature":
        if not s:
            raise ValueError("Invalid key signature: " + s)
        # Key part: "C", "F#", "Bb", "Gs" (s = sharp)
        if len(s) == 1:
            key_part = s
        elif len(s) >= 2 and s[1] in "b#s":
            key_part = s[:2].replace("s", "#")
        else:
            key_part = s[0]
        suffix = s[len(key_part) :].strip()
        if len(suffix) > 3:
            suffix = suffix[:3]
        mode = KeyMode.parse_mode(suffix)
        if mode is None:
            raise ValueError("Invalid key signature: " + s)
        keys = _mode_to_keys(mode)
        if not keys:
            raise ValueError("Invalid key signature: " + s)
        for i, k in enumerate(keys):
            if k.lower() == key_part.lower():
                return cls(sharps_flats=i - 7, mode=mode)
        raise ValueError("Invalid key signature: " + s)


C_MAJOR = KeySignature(0, KeyMode.MAJOR)
