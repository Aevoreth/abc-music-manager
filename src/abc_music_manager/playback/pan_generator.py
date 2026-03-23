"""
Maestro-style pan: instrument-based offsets + part-title keywords (left/right/center).
From PanGenerator.java.
Source: https://github.com/NikolaiVChr/maestro (fork of digero/maestro).
"""

from __future__ import annotations

import re
from typing import Optional

CENTER = 64
MAX_NARROW = 15
VERY_NARROW = 20
NARROW = 25
MID_NARROW = 30
MID_WIDE = 35
SOMEWHAT_WIDE = 40
VERY_WIDE = 45
MAX_WIDE = 50

_LEFT_REGEX = re.compile(r"\b(left|links|gauche)\b")
_RIGHT_REGEX = re.compile(r"\b(right|rechts|droite)\b")
_CENTER_REGEX = re.compile(r"\b(middle|center|zentrum|mitte|centre)\b")

# MIDI program -> pan category: (offset, is_negative_for_first)
# offset: positive = right of center, negative = left. First instance gets +, second -, third center.
# From PanGenerator: fiddle=-MAX_WIDE, harp=-VERY_WIDE, flute=-SOMEWHAT_WIDE, bagpipe=-MID_NARROW,
# horn=-NARROW, cowbell=-MAX_NARROW, drum=+MAX_NARROW, pibgorn=+VERY_NARROW, theorbo=+NARROW,
# lute=+MID_WIDE, clarinet=+VERY_WIDE, bassoon=+MAX_WIDE
_MIDI_TO_PAN_OFFSET: dict[int, int] = {
    # BASIC_FIDDLE family -> -MAX_WIDE
    41: -MAX_WIDE,  # basic fiddle
    51: -MAX_WIDE,  # lonely mountain fiddle
    120: -MAX_WIDE,  # student fiddle
    40: -MAX_WIDE,  # bardic fiddle
    # BASIC_HARP family -> -VERY_WIDE
    46: -VERY_WIDE,  # basic harp
    27: -VERY_WIDE,  # misty mountain harp
    110: -VERY_WIDE,  # sprightly fiddle
    # BASIC_FLUTE -> -SOMEWHAT_WIDE
    73: -SOMEWHAT_WIDE,
    # BASIC_BAGPIPE -> -MID_NARROW
    109: -MID_NARROW,
    # BASIC_HORN -> -NARROW
    69: -NARROW,
    # BASIC_COWBELL -> -MAX_NARROW
    115: -MAX_NARROW,
    114: -MAX_NARROW,  # moor cowbell
    # BASIC_DRUM -> +MAX_NARROW
    118: MAX_NARROW,
    # BASIC_PIBGORN -> +VERY_NARROW
    84: VERY_NARROW,
    # BASIC_THEORBO -> +NARROW
    32: NARROW,
    # LUTE_OF_AGES family -> +MID_WIDE
    24: MID_WIDE,  # lute of ages
    25: MID_WIDE,  # basic lute
    45: MID_WIDE,  # traveller's trusty fiddle
    # BASIC_CLARINET -> +VERY_WIDE
    71: VERY_WIDE,
    # BASIC_BASSOON -> +MAX_WIDE
    70: MAX_WIDE,
    68: MAX_WIDE,  # brusque bassoon
    63: MAX_WIDE,  # lonely mountain bassoon
}
_DEFAULT_OFFSET = 0  # center for unknown


def get_pan(
    midi_program: int,
    part_title: Optional[str] = None,
    pan_modifier: int = 100,
    count_by_program: Optional[dict[int, int]] = None,
) -> int:
    """
    Get MIDI pan value (0-127) for a part.
    midi_program: MIDI program number (0-127)
    part_title: optional part title for left/right/center keywords
    pan_modifier: 0-100, scales stereo width (100 = full)
    count_by_program: mutable dict to track instance count per program (for L/R alternation)
    """
    count = count_by_program or {}
    idx = count.get(midi_program, 0)
    count[midi_program] = idx + 1

    base_offset = _MIDI_TO_PAN_OFFSET.get(midi_program, _DEFAULT_OFFSET)
    sign = (1, -1, 0)[idx % 3]  # alternate: first +, second -, third center
    pan = CENTER + sign * abs(base_offset)

    if pan_modifier != 100:
        pan = pan - CENTER
        pan = int(pan * (pan_modifier / 100.0))
        pan = pan + CENTER

    title_lower = (part_title or "").lower()
    if _LEFT_REGEX.search(title_lower):
        pan = CENTER - int(MAX_WIDE * (pan_modifier / 100.0))
    elif _RIGHT_REGEX.search(title_lower):
        pan = CENTER + int(MAX_WIDE * (pan_modifier / 100.0))
    elif _CENTER_REGEX.search(title_lower):
        pan = CENTER

    return max(0, min(127, pan))
