"""
Map LOTRO instrument names (%%part-name, %%made-for) to MIDI program numbers.
Based on Maestro LotroInstrument and MidiInstrument enums.
"""

from __future__ import annotations

import re
from typing import Optional

# LOTRO instrument name (or nickname) -> MIDI program number (0-127)
# From Maestro LotroInstrument -> MidiInstrument mapping
_INSTRUMENT_TO_MIDI: dict[str, int] = {
    # Harps
    "basic harp": 46,  # ORCHESTRA_HARP
    "harp": 46,
    "misty mountain harp": 27,  # CLEAN_ELEC_GUITAR
    "mm harp": 27,
    "mmh": 27,
    # Lutes
    "basic lute": 25,  # STEEL_STRING_GUITAR
    "new lute": 25,
    "lute of ages": 24,  # NYLON_GUITAR
    "lute": 24,
    "loa": 24,
    "guitar": 24,
    "basic theorbo": 32,  # ACOUSTIC_BASS
    "theorbo": 32,
    "theo": 32,
    "bass": 32,
    # Fiddles
    "traveller's trusty fiddle": 45,  # PIZZICATO_STRINGS
    "traveller's fiddle": 45,
    "trusty fiddle": 45,
    "tt fiddle": 45,
    "ttf": 45,
    "bardic fiddle": 40,  # VIOLIN
    "bardic": 40,
    "violin": 40,
    "basic fiddle": 41,  # VIOLA
    "bsc fiddle": 41,
    "lonely mountain fiddle": 51,  # SYNTH_STRING_2
    "lm fiddle": 51,
    "lmf": 51,
    "sprightly fiddle": 110,  # FIDDLE
    "sprightly": 110,
    "sp fiddle": 110,
    "student's fiddle": 120,  # GUITAR_FRET_NOISE
    "student fiddle": 120,
    "stud fiddle": 120,
    # Winds
    "basic bagpipe": 109,  # BAG_PIPE
    "bagpipe": 109,
    "bag pipes": 109,
    "pipes": 109,
    "basic bassoon": 70,  # BASSOON
    "bassoon": 70,
    "brusque bassoon": 68,  # OBOE
    "brusk bassoon": 68,
    "lonely mountain bassoon": 63,  # SYNTH_BRASS_2
    "lm bassoon": 63,
    "lmb": 63,
    "basic clarinet": 71,  # CLARINET
    "clarinet": 71,
    "clari": 71,
    "basic flute": 73,  # FLUTE
    "flute": 73,
    "basic horn": 69,  # ENGLISH_HORN
    "horn": 69,
    "basic pibgorn": 84,  # CHARANG
    "pibgorn": 84,
    "pib": 84,
    # Percussion
    "basic cowbell": 115,  # WOODBLOCK
    "cowbell": 115,
    "moor cowbell": 114,  # STEEL_DRUMS
    "more cowbell": 114,
    "moor": 114,
    "basic drum": 118,  # SYNTH_DRUM
    "drum": 118,
    "drums": 118,
    # Hand-knells (Glockenspiel) — check longer keys first for substring match
    "jaunty hand-knells": 9,  # GLOCKENSPIEL
    "jaunty hand knells": 9,
    "jaunty hand-knell": 9,
    "jaunty handknells": 9,
    "hand-knells": 9,
    "hand knells": 9,
    "handknells": 9,
    "hand-knell": 9,
    "hand bells": 9,
    "handbells": 9,
    "jhk": 9,
    "glockenspiel": 9,
}


def _normalize_name(s: str) -> str:
    """Lowercase, collapse whitespace, strip."""
    return " ".join((s or "").lower().split()).strip()


# MIDI programs that have natural decay (plucked, percussive) - notes should be held longer to ring out
# GM categories: Chromatic Percussion (8-15), Guitar (24-31), Bass (32-39), Pizzicato (45), Harp (46),
# Percussive (112-119)
_NON_SUSTAINED_MIDI_PROGRAMS: frozenset[int] = frozenset({
    8, 9, 10, 11, 12, 13, 14, 15,   # Chromatic percussion (glockenspiel, etc.)
    24, 25, 26, 27, 28, 29, 30, 31,  # Guitar
    32, 33, 34, 35, 36, 37, 38, 39,  # Bass
    45,   # Pizzicato strings
    46,   # Harp
    112, 113, 114, 115, 116, 117, 118, 119,  # Percussive
})


def is_non_sustained_instrument(midi_program: int) -> bool:
    """True if instrument has natural decay (plucked, percussive) and benefits from extended note hold."""
    return midi_program in _NON_SUSTAINED_MIDI_PROGRAMS


def resolve_instrument_to_midi_program(part_name: Optional[str], made_for: Optional[str]) -> int:
    """
    Resolve %%part-name or %%made-for to MIDI program number.
    Returns 24 (Lute of Ages / Nylon Guitar) as default if no match.
    """
    for raw in (part_name, made_for):
        if not raw:
            continue
        name = _normalize_name(raw)
        if not name:
            continue
        # Exact match first
        if name in _INSTRUMENT_TO_MIDI:
            return _INSTRUMENT_TO_MIDI[name]
        # Substring match: prefer longest key that matches (e.g. "hand-knells" over "hand")
        best_key: Optional[str] = None
        for key, prog in _INSTRUMENT_TO_MIDI.items():
            if key in name or name in key:
                if best_key is None or len(key) > len(best_key):
                    best_key = key
        if best_key is not None:
            return _INSTRUMENT_TO_MIDI[best_key]
    return 24  # LUTE_OF_AGES default
