"""
Dynamics: pp–ffff velocity mapping for ABC and MIDI.
From Dynamics.java.
"""

from __future__ import annotations

from enum import Enum


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


class Dynamics(Enum):
    pppp = (4, 61)
    ppp = (16, 61)
    pp = (32, 75)
    p = (48, 87)
    mp = (64, 97)
    mf = (80, 106)
    f = (96, 115)
    ff = (112, 123)
    fff = (127, 127)
    ffff = (144, 127)

    def __init__(self, midi_vol: int, abc_vol: int) -> None:
        self.midi_vol = midi_vol
        self.abc_vol = abc_vol

    def get_vol(self, use_lotro: bool) -> int:
        v = self.abc_vol if use_lotro else self.midi_vol
        return _clamp(v, 0, 127)

    @classmethod
    def from_string(cls, s: str) -> "Dynamics":
        try:
            return cls[s.lower()]
        except KeyError:
            raise ValueError(f"Unknown dynamics: {s}")

    @classmethod
    def default(cls) -> "Dynamics":
        return cls.mf


DEFAULT = Dynamics.mf
MAXIMUM = Dynamics.ffff
MINIMUM = Dynamics.pppp
