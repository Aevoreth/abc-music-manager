"""
Note: MIDI note IDs, from_id, playable range.
From Note.java. Simplified for ABC-to-MIDI conversion.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# REST has id -1
REST_ID = -1

# MIDI note range: C-1 (0) to G9 (127)
MIN_ID = 0
MAX_ID = 127

# LOTRO playable range
MIN_PLAYABLE_ID = 36  # C2
MAX_PLAYABLE_ID = 72  # C5

# Chromatic positions of white keys (C=0, D=2, E=4, F=5, G=7, A=9, B=11)
WHITE_KEY_CHROMAS = {0, 2, 4, 5, 7, 9, 11}


@dataclass(frozen=True)
class Note:
    """A MIDI note with id and naturalId for key signature lookup."""

    id: int
    natural_id: int
    octave: int
    abc: str

    def is_playable(self) -> bool:
        return MIN_PLAYABLE_ID <= self.id <= MAX_PLAYABLE_ID


# Precomputed lookup: id -> Note
_ID_TO_NOTE: dict[int, Note] = {}


def _build_note(id_val: int) -> Note:
    """Build a Note for the given MIDI id."""
    if id_val in (0, 2, 4, 5, 7, 9, 11) or (id_val > 0 and (id_val % 12) in WHITE_KEY_CHROMAS):
        natural_id = id_val
    elif id_val > 0:
        chroma = id_val % 12
        # Sharp: natural is semitone below
        if chroma in (1, 3, 6, 8, 10):  # C#, D#, F#, G#, A#
            natural_id = id_val - 1
        else:
            natural_id = id_val + 1
    else:
        natural_id = id_val

    octave = (id_val // 12) - 1 if id_val >= 0 else 0
    # ABC: ^ for sharp, _ for flat, letter + octave marks
    if id_val < 0:
        abc = "z"
    else:
        chroma = id_val % 12
        letters = "CCDDEFFGGAAB"
        accidentals = [0, 1, 0, 1, 0, 0, 1, 0, 1, 0, 1, 0]  # 1=sharp
        letter = letters[chroma]
        acc = accidentals[chroma]
        if acc:
            abc = "^" + letter.lower() if octave >= 4 else "^" + letter.upper()
        else:
            abc = letter.lower() if octave >= 4 else letter.upper()
        if octave < 3:
            abc += "," * (3 - octave)
        elif octave > 4:
            abc += "'" * (octave - 4)
    return Note(id=id_val, natural_id=natural_id, octave=octave, abc=abc)


def _ensure_lookup() -> None:
    global _ID_TO_NOTE
    if not _ID_TO_NOTE:
        _ID_TO_NOTE[REST_ID] = Note(id=REST_ID, natural_id=REST_ID, octave=0, abc="z")
        for i in range(MIN_ID, MAX_ID + 1):
            _ID_TO_NOTE[i] = _build_note(i)


def from_id(id_val: int) -> Optional[Note]:
    """Return Note for MIDI id, or None if out of range."""
    _ensure_lookup()
    return _ID_TO_NOTE.get(id_val)


def is_playable(id_val: int) -> bool:
    return MIN_PLAYABLE_ID <= id_val <= MAX_PLAYABLE_ID


# Constants for convenience
REST = Note(id=REST_ID, natural_id=REST_ID, octave=0, abc="z")

_ensure_lookup()
MIN_PLAYABLE = _ID_TO_NOTE[MIN_PLAYABLE_ID]
MAX_PLAYABLE = _ID_TO_NOTE[MAX_PLAYABLE_ID]
