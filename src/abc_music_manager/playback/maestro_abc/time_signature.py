"""
Time signature: meter parsing, MIDI meta event.
From TimeSignature.java. For non-power-of-2 denominators, use 4/4 for MIDI meta.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

MAX_DENOMINATOR = 8


def _floor_log2(n: int) -> int:
    if n <= 0:
        return -1
    return n.bit_length() - 1


def _is_power_of_2(n: int) -> bool:
    return n > 0 and n == (1 << _floor_log2(n))


@dataclass(frozen=True)
class TimeSignature:
    numerator: int
    denominator: int

    def __post_init__(self) -> None:
        if self.denominator == 0 or not _is_power_of_2(self.denominator):
            raise ValueError("Denominator must be a power of 2")
        if self.denominator > MAX_DENOMINATOR:
            raise ValueError(f"Denominator must be <= {MAX_DENOMINATOR}")
        if self.numerator > 255:
            raise ValueError("Numerator must be < 256")

    def is_compound(self) -> bool:
        return (self.numerator % 3) == 0

    def __str__(self) -> str:
        return f"{self.numerator}/{self.denominator}"


FOUR_FOUR = TimeSignature(4, 4)


def parse_time_signature(s: str, strict: bool = False) -> TimeSignature:
    """Parse M: field. Returns 4/4 for invalid or non-power-of-2 denominators if not strict."""
    s = s.strip()
    if s == "C":
        return TimeSignature(4, 4)
    if s == "C|":
        return TimeSignature(2, 2)
    parts = re.split(r"[/:\s]+", s)
    parts = [p.strip() for p in parts if p.strip()]
    if len(parts) != 2:
        raise ValueError(f'Invalid time signature: "{s}" (expected e.g. 4/4)')
    num = int(parts[0])
    denom = int(parts[1])
    if not strict and (denom > MAX_DENOMINATOR or not _is_power_of_2(denom)):
        return FOUR_FOUR
    return TimeSignature(num, denom)


def safe_time_signature(num: int, denom: int) -> TimeSignature:
    """Return TimeSignature or FOUR_FOUR if denominator is not power-of-2."""
    try:
        return TimeSignature(num, denom)
    except ValueError:
        return FOUR_FOUR
