"""
Band layout pan: compute part_number -> pan from song layout + band layout.
"""

from __future__ import annotations

import sqlite3
from typing import Optional

from ..db.band_repo import list_layout_slots
from ..db.setlist_repo import get_setlist_band_assignments
from ..db.song_layout_repo import get_song_layout_assignments
from ..playback.band_layout_pan import (
    _compute_listener_position,
    angle_based_pan_for_slot,
)


def get_part_pan_map(
    conn: sqlite3.Connection,
    song_layout_id: Optional[int],
    band_layout_id: Optional[int],
    setlist_item_id: Optional[int] = None,
) -> Optional[dict[int, int]]:
    """
    Build part_number (X: value) -> MIDI pan (0-127) from song layout + band layout + setlist overrides.
    Uses SongLayoutAssignment for base assignments; SetlistBandAssignment overrides when setlist_item_id set.
    Otherwise fall back to slot order: track 1 = first slot (by y,x), etc.
    Returns None only when band_layout_id is missing or band layout has no slots.
    """
    if not band_layout_id:
        return None
    slots = list_layout_slots(conn, band_layout_id)
    if not slots:
        return None

    listener_x, listener_y = _compute_listener_position(slots)
    result: dict[int, int] = {}

    layout_assigns: dict[int, int | None] = {}
    if song_layout_id:
        for a in get_song_layout_assignments(conn, song_layout_id):
            layout_assigns[a.player_id] = a.part_number

    overrides: dict[int, int | None] = {}
    if setlist_item_id:
        overrides = get_setlist_band_assignments(conn, setlist_item_id)

    for s in slots:
        eff = overrides.get(s.player_id) if s.player_id in overrides else layout_assigns.get(s.player_id)
        if eff is None:
            continue
        result[eff] = angle_based_pan_for_slot(s.x, s.y, listener_x, listener_y)

    if not result:
        for part_num, slot in enumerate(slots, start=1):
            result[part_num] = angle_based_pan_for_slot(
                slot.x, slot.y, listener_x, listener_y
            )

    return result if result else None
