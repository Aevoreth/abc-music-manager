"""
Band-layout pan: map slot (x, y) to pan. Listener at top-center, facing band.
"""

from __future__ import annotations

from typing import Optional

# From band_layout_grid: X_MIN=-145, X_MAX=145, Y_MIN=-105, Y_MAX=105
# Listener at top-center: (0, Y_MIN) = (0, -105), facing down (positive Y)
# x < 0 -> left, x > 0 -> right
# Linear map: x in [X_MIN, X_MAX] -> pan in [14, 114] (MIDI 0-127, center 64)
X_MIN, X_MAX = -145, 145
Y_MIN, Y_MAX = -105, 105
PAN_LEFT = 14
PAN_RIGHT = 114
PAN_CENTER = 64


def slot_to_pan(x: int, y: int) -> int:
    """
    Map band layout slot (x, y) to MIDI pan (0-127).
    Listener at top-center (0, Y_MIN), facing band. x negative = left, x positive = right.
    """
    if X_MAX == X_MIN:
        return PAN_CENTER
    # Linear: x=-145 -> 14, x=0 -> 64, x=145 -> 114
    t = (x - X_MIN) / (X_MAX - X_MIN)
    pan = PAN_LEFT + t * (PAN_RIGHT - PAN_LEFT)
    return max(0, min(127, int(round(pan))))


def get_pan_for_slot(x: Optional[int], y: Optional[int]) -> int:
    """Get pan for slot; returns center if position unknown."""
    if x is None:
        return PAN_CENTER
    return slot_to_pan(x, y if y is not None else 0)
