"""
Per-tune state: meter, tempo, key, PPQN, instrument, dynamics.
From TuneInfo.java.
"""

from __future__ import annotations

import re
from typing import Optional

from .abc_constants import DEFAULT_NOTE_TICKS
from .dynamics import Dynamics
from .key_signature import KeySignature, C_MAJOR
from .time_signature import TimeSignature, FOUR_FOUR, safe_time_signature

DEFAULT_MIDI_PROGRAM = 24  # Lute of Ages


class TuneInfo:
    """Per-tune/part state for ABC conversion."""

    def __init__(self) -> None:
        self.part_number = 0
        self.title = ""
        self.title_is_from_extended_info = False
        self.key = C_MAJOR
        self.meter_numerator = 4
        self.meter_denominator = 4
        self.primary_tempo_bpm = 120
        self._cur_part_tempo_map: dict[int, int] = {}
        self._all_parts_tempo_map: dict[int, int] = {}
        self.instrument_midi_program = DEFAULT_MIDI_PROGRAM
        self.instrument_set = False
        self.instrument_set_hard = False
        self.dynamics = Dynamics.mf
        self.compound_meter = False
        self.note_divisor_num = -1
        self.note_divisor_denom = 1
        self.tick_factor = 16
        self.ppqn = 0
        self._calc_ppqn()

    def new_part(self, part_number: int) -> None:
        self.part_number = part_number
        self.instrument_midi_program = DEFAULT_MIDI_PROGRAM
        self.instrument_set = False
        self.dynamics = Dynamics.mf
        self.title = ""
        self.title_is_from_extended_info = False
        self._cur_part_tempo_map.clear()

    def set_title(self, title: str, from_extended_info: bool) -> None:
        if from_extended_info or not self.title_is_from_extended_info:
            self.title = title
            self.title_is_from_extended_info = from_extended_info

    def set_key(self, s: str) -> None:
        self.key = KeySignature.from_string(s)

    def set_note_divisor(self, s: str) -> None:
        self._parse_note_divisor(s)
        self._calc_ppqn()

    def get_l_num(self) -> int:
        return 1 if self.note_divisor_num < 0 else self.note_divisor_num

    def get_l_denom(self) -> int:
        if self.note_divisor_num < 0:
            return 16 if (4 * self.meter_numerator / self.meter_denominator) < 3 else 8
        return self.note_divisor_denom

    def _calc_ppqn(self) -> None:
        self.tick_factor = 16
        self.ppqn = DEFAULT_NOTE_TICKS * self.tick_factor // self.meter_denominator

    def get_whole_note_time(self) -> float:
        if self.note_divisor_num > 0:
            return (
                self.meter_denominator
                * self.note_divisor_num
                * 60.0
                / (self.primary_tempo_bpm * self.note_divisor_denom)
            )
        l_val = 1.0 / 16 if (self.meter_numerator / self.meter_denominator) < 0.75 else 1.0 / 8
        return (self.meter_denominator * l_val * 60.0) / self.primary_tempo_bpm

    def set_meter(self, s: str) -> None:
        s = s.strip()
        if s == "C":
            self.meter_numerator = 4
            self.meter_denominator = 4
        elif s == "C|":
            self.meter_numerator = 2
            self.meter_denominator = 2
        else:
            parts = re.split(r"[/:\s]+", s)
            parts = [p.strip() for p in parts if p.strip()]
            if len(parts) != 2:
                raise ValueError(f'Invalid time signature: "{s}" (expected e.g. 4/4)')
            self.meter_numerator = int(parts[0])
            self.meter_denominator = int(parts[1])
        self._calc_ppqn()
        self.compound_meter = (self.meter_numerator % 3) == 0

    def get_meter(self) -> TimeSignature:
        return safe_time_signature(self.meter_numerator, self.meter_denominator)

    def _parse_tempo(self, s: str) -> int:
        parts = s.split("=")
        if len(parts) == 1:
            bpm = int(parts[0])
        elif len(parts) == 2:
            bpm = int(parts[1].strip())
        else:
            raise ValueError("Unable to read tempo")
        if bpm < 1 or bpm > 10000:
            raise ValueError(f"Tempo {bpm} out of range (1-10000)")
        return bpm

    def set_primary_tempo_bpm(self, s: str) -> None:
        self.primary_tempo_bpm = self._parse_tempo(s)
        if 0 not in self._all_parts_tempo_map:
            self._all_parts_tempo_map[0] = self.primary_tempo_bpm
        if 0 not in self._cur_part_tempo_map:
            self._cur_part_tempo_map[0] = self.primary_tempo_bpm

    def add_tempo_event(self, tick: int, s: str) -> None:
        bpm = self._parse_tempo(s)
        self._all_parts_tempo_map[tick] = bpm
        self._cur_part_tempo_map[tick] = bpm

    def get_current_tempo_bpm(self, tick: int) -> int:
        # floorEntry: largest key <= tick
        candidates = [t for t in self._cur_part_tempo_map if t <= tick]
        if not candidates:
            return self.primary_tempo_bpm
        best = max(candidates)
        return self._cur_part_tempo_map[best]

    def get_all_parts_tempo_map(self) -> dict[int, int]:
        return self._all_parts_tempo_map

    def _parse_note_divisor(self, s: str) -> float:
        parts = re.split(r"[/:\s]+", s.strip())
        parts = [p.strip() for p in parts if p.strip()]
        if len(parts) != 2:
            raise ValueError(f'Invalid note length: "{s}" (e.g. 1/4)')
        num = int(parts[0])
        denom = int(parts[1])
        if num < 1:
            raise ValueError("Note length numerator must be positive")
        if denom < 1:
            raise ValueError("Note length denominator must be positive")
        self.note_divisor_num = num
        self.note_divisor_denom = denom
        return num / denom

    def set_instrument(self, midi_program: int, definitive: bool = False) -> None:
        self.instrument_midi_program = midi_program
        self.instrument_set = True
        self.instrument_set_hard = definitive

    def is_instrument_set(self) -> bool:
        return self.instrument_set

    def is_instrument_definitive_set(self) -> bool:
        return self.instrument_set and self.instrument_set_hard

    def set_dynamics(self, s: str) -> None:
        self.dynamics = Dynamics.from_string(s)

    def get_part_number(self) -> int:
        return self.part_number

    def get_title(self) -> str:
        return self.title

    def get_key(self) -> KeySignature:
        return self.key

    def get_ppqn(self) -> int:
        return self.ppqn

    def get_tick_factor(self) -> int:
        return self.tick_factor

    def is_compound_meter(self) -> bool:
        return self.compound_meter

    def get_primary_tempo_bpm(self) -> int:
        return self.primary_tempo_bpm

    def get_instrument_midi_program(self) -> int:
        return self.instrument_midi_program

    def get_dynamics(self) -> Dynamics:
        return self.dynamics
