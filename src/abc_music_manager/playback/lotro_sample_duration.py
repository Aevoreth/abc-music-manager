"""
Per-sample note durations for LOTRO instruments (microseconds).
From Maestro LotroInstrumentSampleDuration.java and noteDurations.txt.
"""

from __future__ import annotations

from functools import lru_cache
from importlib import resources
from typing import Optional

from abc_music_manager.playback import data as playback_data

from .maestro_abc.abc_constants import COWBELL_NOTE_ID

_COWBELL_NAMES = frozenset({"Basic Cowbell", "Moor Cowbell"})


@lru_cache(maxsize=1)
def _load_durations() -> dict[str, dict[int, int]]:
    db: dict[str, dict[int, int]] = {}
    try:
        text = resources.files(playback_data).joinpath(
            "noteDurations.txt"
        ).read_text(encoding="utf-8")
    except (FileNotFoundError, OSError, TypeError):
        return db

    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split(",")]
        if len(parts) != 3:
            continue
        instr, note_str, dura_str = parts
        try:
            note = int(note_str)
            dura = int(dura_str)
        except ValueError:
            continue
        db.setdefault(instr, {})[note] = dura
        if instr == "Basic Fiddle" and note >= 43:
            db.setdefault("Student's Fiddle", {})[note] = dura
    return db


def get_sample_duration_micros(friendly_name: str, note_id: int) -> Optional[int]:
    """
    Return sample duration in microseconds for an instrument/note, or None if unknown.
    Cowbell instruments always look up using COWBELL_NOTE_ID (71), matching Maestro.
    """
    db = _load_durations()
    instr_map = db.get(friendly_name)
    if instr_map is None:
        return None
    lookup_note = COWBELL_NOTE_ID if friendly_name in _COWBELL_NAMES else note_id
    return instr_map.get(lookup_note)
