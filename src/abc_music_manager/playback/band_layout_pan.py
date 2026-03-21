"""
Band-layout pan: map slot (x, y) to pan via listener position and angle.

Listener is positioned in front of the band (top = front). Pan reflects where
each player falls on a semicircle arc from the listener's perspective.
"""

from __future__ import annotations

import math
from typing import Optional, Sequence

# From band_layout_grid: X_MIN=-145, X_MAX=145, Y_MIN=-105, Y_MAX=105
# Top = front (smaller y = closer to audience)
X_MIN, X_MAX = -145, 145
Y_MIN, Y_MAX = -105, 105
PAN_LEFT = 0
PAN_RIGHT = 127
PAN_CENTER = 64


def slot_to_pan(x: int, y: int) -> int:
    """
    Legacy: linear x mapping. Kept for backwards compatibility.
    Prefer angle_based_pan_for_slot when listener position is known.
    """
    if X_MAX == X_MIN:
        return PAN_CENTER
    t = (x - X_MIN) / (X_MAX - X_MIN)
    pan = PAN_LEFT + t * (PAN_RIGHT - PAN_LEFT)
    return max(0, min(127, int(round(pan))))


def get_pan_for_slot(x: Optional[int], y: Optional[int]) -> int:
    """Get pan for slot (legacy x-only); returns center if position unknown."""
    if x is None:
        return PAN_CENTER
    return slot_to_pan(x, y if y is not None else 0)


def _compute_listener_position(slots: Sequence) -> tuple[float, float]:
    """
    Listener at front-center of band. Top = front (min y).
    Returns (listener_x, listener_y).
    """
    if not slots:
        return (0.0, float(Y_MIN))
    xs = [s.x for s in slots]
    ys = [s.y for s in slots]
    listener_x = (min(xs) + max(xs)) / 2.0
    listener_y = float(min(ys))  # Front row = closest to audience
    return (listener_x, listener_y)


def angle_based_pan_for_slot(
    slot_x: int,
    slot_y: int,
    listener_x: float,
    listener_y: float,
) -> int:
    """
    Map slot position to MIDI pan (0-127) from listener's perspective.
    Listener faces the band (positive y = into stage). Angle from listener
    to slot maps to semicircle: left -> PAN_LEFT, center -> PAN_CENTER, right -> PAN_RIGHT.
    """
    dx = slot_x - listener_x
    dy = slot_y - listener_y
    if dx == 0 and dy == 0:
        return PAN_CENTER
    angle = math.atan2(dx, dy)  # -pi to pi; 0 = straight ahead
    # Map [-pi/2, pi/2] to [PAN_LEFT, PAN_RIGHT]. Clamp angle to semicircle.
    angle = max(-math.pi / 2, min(math.pi / 2, angle))
    t = (angle + math.pi / 2) / math.pi  # 0 to 1
    pan = PAN_LEFT + t * (PAN_RIGHT - PAN_LEFT)
    pan = max(0, min(127, int(round(pan))))
    return 127 - pan  # Flip L/R: listener perspective (left=left) was coming out swapped
