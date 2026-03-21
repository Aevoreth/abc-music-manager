"""
Simplified AbcInfo: metadata, parts, time/key sig for playback.
From AbcInfo.java - minimal subset for ABC-to-MIDI conversion.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .abc_field import AbcField
from .key_signature import KeySignature, C_MAJOR
from .time_signature import TimeSignature, FOUR_FOUR


@dataclass
class PartInfo:
    """Per-part info for track naming and pan."""

    number: int = 1
    midi_program: int = 24
    name: Optional[str] = None
    name_is_from_extended_info: bool = False
    user_pan: Optional[str] = None  # "auto" or "0"-"127" from %%user-pan


class AbcInfo:
    """Metadata and part info for ABC conversion."""

    def __init__(self) -> None:
        self._metadata: dict[str, str] = {}
        self._part_info: dict[int, PartInfo] = {}
        self._title: Optional[str] = None
        self._composer: Optional[str] = None
        self._time_signature = FOUR_FOUR
        self._key_signature = C_MAJOR
        self._primary_tempo_bpm = 120

    def reset(self) -> None:
        self._metadata.clear()
        self._part_info.clear()
        self._title = None
        self._composer = None
        self._time_signature = FOUR_FOUR
        self._key_signature = C_MAJOR
        self._primary_tempo_bpm = 120

    def set_metadata(self, key: str, value: str) -> None:
        self._metadata[key.upper()] = value
        if key.upper() == "T":
            self._title = value or self._title
        elif key.upper() == "C":
            self._composer = value or self._composer

    def set_extended_metadata(self, field: AbcField, value: str) -> None:
        if field == AbcField.SONG_TITLE:
            self._title = value or self._title
        elif field == AbcField.SONG_COMPOSER:
            self._composer = value or self._composer

    def set_part_number(self, track_number: int, part_number: int) -> None:
        self._ensure_part(track_number)
        self._part_info[track_number].number = part_number

    def set_part_name(self, track_number: int, name: str, from_extended_info: bool) -> None:
        self._ensure_part(track_number)
        self._part_info[track_number].name = name or None
        self._part_info[track_number].name_is_from_extended_info = from_extended_info

    def set_part_instrument(self, track_number: int, midi_program: int) -> None:
        self._ensure_part(track_number)
        self._part_info[track_number].midi_program = midi_program

    def set_part_user_pan(self, track_number: int, value: str) -> None:
        self._ensure_part(track_number)
        self._part_info[track_number].user_pan = value.strip().lower() if value else None

    def get_part_user_pan(self, track_number: int) -> Optional[str]:
        p = self._part_info.get(track_number)
        return (p.user_pan if p else None) if p else None

    def set_time_signature(self, ts: TimeSignature) -> None:
        self._time_signature = ts

    def set_key_signature(self, ks: KeySignature) -> None:
        self._key_signature = ks

    def set_primary_tempo_bpm(self, bpm: int) -> None:
        self._primary_tempo_bpm = bpm

    def _ensure_part(self, track_number: int) -> None:
        if track_number not in self._part_info:
            self._part_info[track_number] = PartInfo(number=track_number)

    def get_title(self) -> str:
        return self._title or self._metadata.get("T", "") or ""

    def get_part_name(self, track_number: int) -> str:
        p = self._part_info.get(track_number)
        return (p.name or "") if p else ""

    def get_part_instrument(self, track_number: int) -> int:
        p = self._part_info.get(track_number)
        return p.midi_program if p else 24

    def get_part_number(self, track_number: int) -> int:
        """Part number (from ABC X: field) for this track. Matches Song.parts and assignment panel."""
        p = self._part_info.get(track_number)
        return p.number if p else track_number

    def get_time_signature(self) -> TimeSignature:
        return self._time_signature

    def get_key_signature(self) -> KeySignature:
        return self._key_signature

    def get_primary_tempo_bpm(self) -> int:
        return self._primary_tempo_bpm
