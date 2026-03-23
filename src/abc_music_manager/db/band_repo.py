"""Band, BandMember, BandLayout, BandLayoutSlot CRUD. DATA_MODEL §4."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class BandRow:
    id: int
    name: str
    notes: str | None
    created_at: str
    updated_at: str


@dataclass
class BandLayoutRow:
    id: int
    band_id: int
    name: str
    created_at: str
    updated_at: str


@dataclass
class BandLayoutSlotRow:
    id: int
    band_layout_id: int
    player_id: int
    x: int
    y: int
    width_units: int
    height_units: int
    created_at: str
    updated_at: str


def list_bands(conn: sqlite3.Connection) -> list[BandRow]:
    cur = conn.execute(
        "SELECT id, name, created_at, updated_at, notes FROM Band ORDER BY sort_order, name"
    )
    return [BandRow(id=r[0], name=r[1], notes=r[4], created_at=r[2], updated_at=r[3]) for r in cur.fetchall()]


def add_band(conn: sqlite3.Connection, name: str, notes: str | None = None) -> int:
    now = _now()
    sort_cur = conn.execute("SELECT COALESCE(MAX(sort_order), -1) + 1 FROM Band")
    sort_order = sort_cur.fetchone()[0]
    cur = conn.execute(
        "INSERT INTO Band (name, notes, sort_order, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        (name.strip(), notes or None, sort_order, now, now),
    )
    conn.commit()
    return cur.lastrowid


def reorder_bands(conn: sqlite3.Connection, band_ids_in_order: list[int]) -> None:
    """Set sort_order 0, 1, 2, ... for the given band ids in order."""
    now = _now()
    for sort_order, band_id in enumerate(band_ids_in_order):
        conn.execute(
            "UPDATE Band SET sort_order = ?, updated_at = ? WHERE id = ?",
            (sort_order, now, band_id),
        )
    conn.commit()


def duplicate_band(conn: sqlite3.Connection, band_id: int) -> int:
    """
    Create a copy of the band with name suffixed " - Copy", notes, members, layouts and slots.
    Returns the new band id. New band is placed at end of list.
    """
    cur = conn.execute("SELECT name, notes FROM Band WHERE id = ?", (band_id,))
    row = cur.fetchone()
    if not row:
        raise ValueError(f"Band {band_id} not found")
    name, notes = row[0], row[1]
    new_name = f"{name} - Copy"
    new_band_id = add_band(conn, new_name, notes)
    for pid in list_band_members(conn, band_id):
        add_band_member(conn, new_band_id, pid)
    for layout in list_band_layouts(conn, band_id):
        new_layout_id = add_band_layout(conn, new_band_id, layout.name)
        for slot in list_layout_slots(conn, layout.id):
            set_layout_slot(
                conn, new_layout_id, slot.player_id, slot.x, slot.y,
                slot.width_units, slot.height_units,
            )
        export_order = get_export_column_order(conn, layout.id)
        if export_order:
            set_export_column_order(conn, new_layout_id, export_order)
    return new_band_id


def update_band(
    conn: sqlite3.Connection,
    band_id: int,
    name: str,
    notes: str | None = None,
) -> None:
    now = _now()
    if notes is not None:
        conn.execute(
            "UPDATE Band SET name = ?, notes = ?, updated_at = ? WHERE id = ?",
            (name.strip(), notes or None, now, band_id),
        )
    else:
        conn.execute("UPDATE Band SET name = ?, updated_at = ? WHERE id = ?", (name.strip(), now, band_id))
    conn.commit()


def delete_band(conn: sqlite3.Connection, band_id: int) -> None:
    conn.execute("DELETE FROM BandLayoutSlot WHERE band_layout_id IN (SELECT id FROM BandLayout WHERE band_id = ?)", (band_id,))
    conn.execute("DELETE FROM BandLayout WHERE band_id = ?", (band_id,))
    conn.execute("DELETE FROM BandMember WHERE band_id = ?", (band_id,))
    conn.execute("DELETE FROM Band WHERE id = ?", (band_id,))
    conn.commit()


def list_band_members(conn: sqlite3.Connection, band_id: int) -> list[int]:
    """Return list of player_ids in this band."""
    cur = conn.execute("SELECT player_id FROM BandMember WHERE band_id = ? ORDER BY player_id", (band_id,))
    return [r[0] for r in cur.fetchall()]


def add_band_member(conn: sqlite3.Connection, band_id: int, player_id: int) -> None:
    conn.execute("INSERT OR IGNORE INTO BandMember (band_id, player_id) VALUES (?, ?)", (band_id, player_id))
    conn.commit()


def remove_band_member(conn: sqlite3.Connection, band_id: int, player_id: int) -> None:
    conn.execute("DELETE FROM BandMember WHERE band_id = ? AND player_id = ?", (band_id, player_id))
    conn.commit()


def list_all_band_layouts(conn: sqlite3.Connection) -> list[tuple[int, str, str]]:
    """Return (layout_id, layout_name, band_name) for all band layouts."""
    cur = conn.execute(
        """SELECT bl.id, bl.name, b.name FROM BandLayout bl JOIN Band b ON b.id = bl.band_id
           ORDER BY b.name, bl.sort_order, bl.id"""
    )
    return [(r[0], r[1], r[2]) for r in cur.fetchall()]


def get_band_layout_display_name(conn: sqlite3.Connection, band_layout_id: int | None) -> str:
    """Return display string for band layout (band name only; one layout per band). Returns '(draft)' if None."""
    if band_layout_id is None:
        return "(draft)"
    for lid, _layout_name, band_name in list_all_band_layouts(conn):
        if lid == band_layout_id:
            return band_name
    return "(unknown)"


def list_band_layouts(conn: sqlite3.Connection, band_id: int) -> list[BandLayoutRow]:
    cur = conn.execute(
        "SELECT id, band_id, name, created_at, updated_at FROM BandLayout WHERE band_id = ? ORDER BY sort_order, id",
        (band_id,),
    )
    return [BandLayoutRow(id=r[0], band_id=r[1], name=r[2], created_at=r[3], updated_at=r[4]) for r in cur.fetchall()]


def add_band_layout(conn: sqlite3.Connection, band_id: int, name: str) -> int:
    now = _now()
    sort_cur = conn.execute(
        "SELECT COALESCE(MAX(sort_order), -1) + 1 FROM BandLayout WHERE band_id = ?",
        (band_id,),
    )
    sort_order = sort_cur.fetchone()[0]
    cur = conn.execute(
        "INSERT INTO BandLayout (band_id, name, sort_order, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        (band_id, name.strip(), sort_order, now, now),
    )
    conn.commit()
    return cur.lastrowid


def update_band_layout(conn: sqlite3.Connection, layout_id: int, name: str) -> None:
    conn.execute("UPDATE BandLayout SET name = ?, updated_at = ? WHERE id = ?", (name.strip(), _now(), layout_id))
    conn.commit()


def delete_band_layout(conn: sqlite3.Connection, layout_id: int) -> None:
    conn.execute("DELETE FROM BandLayoutSlot WHERE band_layout_id = ?", (layout_id,))
    conn.execute("DELETE FROM BandLayout WHERE id = ?", (layout_id,))
    conn.commit()


def reorder_band_layouts(conn: sqlite3.Connection, band_id: int, layout_ids_in_order: list[int]) -> None:
    """Set sort_order 0, 1, 2, ... for the given layout ids in order."""
    now = _now()
    for sort_order, layout_id in enumerate(layout_ids_in_order):
        conn.execute(
            "UPDATE BandLayout SET sort_order = ?, updated_at = ? WHERE id = ? AND band_id = ?",
            (sort_order, now, layout_id, band_id),
        )
    conn.commit()


def duplicate_band_layout(conn: sqlite3.Connection, layout_id: int, name: str | None = None) -> int:
    """
    Create a copy of the band layout with all slots and export_column_order.
    Returns the new layout id. If name is None, uses "Copy of {original name}".
    """
    cur = conn.execute(
        "SELECT band_id, name, export_column_order FROM BandLayout WHERE id = ?",
        (layout_id,),
    )
    row = cur.fetchone()
    if not row:
        raise ValueError(f"Band layout {layout_id} not found")
    band_id, orig_name, export_order = row[0], row[1], row[2]
    new_name = name.strip() if name and name.strip() else f"Copy of {orig_name}"
    new_layout_id = add_band_layout(conn, band_id, new_name)
    slots = list_layout_slots(conn, layout_id)
    for slot in slots:
        set_layout_slot(
            conn, new_layout_id, slot.player_id, slot.x, slot.y, slot.width_units, slot.height_units
        )
    if export_order:
        conn.execute(
            "UPDATE BandLayout SET export_column_order = ?, updated_at = ? WHERE id = ?",
            (export_order, _now(), new_layout_id),
        )
        conn.commit()
    return new_layout_id


def list_layout_slots(conn: sqlite3.Connection, band_layout_id: int) -> list[BandLayoutSlotRow]:
    cur = conn.execute(
        """SELECT id, band_layout_id, player_id, x, y, width_units, height_units, created_at, updated_at
           FROM BandLayoutSlot WHERE band_layout_id = ? ORDER BY y, x""",
        (band_layout_id,),
    )
    return [
        BandLayoutSlotRow(
            id=r[0], band_layout_id=r[1], player_id=r[2], x=r[3], y=r[4],
            width_units=r[5], height_units=r[6], created_at=r[7], updated_at=r[8],
        )
        for r in cur.fetchall()
    ]


def set_layout_slot(
    conn: sqlite3.Connection,
    band_layout_id: int,
    player_id: int,
    x: int,
    y: int,
    width_units: int = 9,
    height_units: int = 7,
) -> None:
    """Set or update one slot (one player per slot). Remove any existing slot for this player in this layout first."""
    now = _now()
    conn.execute("DELETE FROM BandLayoutSlot WHERE band_layout_id = ? AND player_id = ?", (band_layout_id, player_id))
    conn.execute(
        """INSERT INTO BandLayoutSlot (band_layout_id, player_id, x, y, width_units, height_units, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (band_layout_id, player_id, x, y, width_units, height_units, now, now),
    )
    conn.commit()


def remove_layout_slot(conn: sqlite3.Connection, band_layout_id: int, player_id: int) -> None:
    conn.execute("DELETE FROM BandLayoutSlot WHERE band_layout_id = ? AND player_id = ?", (band_layout_id, player_id))
    conn.commit()


def get_export_column_order(conn: sqlite3.Connection, band_layout_id: int) -> list[int]:
    """Return list of player_ids in CSV export column order. Empty if not set (use default row-major)."""
    cur = conn.execute(
        "SELECT export_column_order FROM BandLayout WHERE id = ?",
        (band_layout_id,),
    )
    row = cur.fetchone()
    if not row or not row[0]:
        return []
    try:
        return json.loads(row[0])
    except (json.JSONDecodeError, TypeError):
        return []


def set_export_column_order(conn: sqlite3.Connection, band_layout_id: int, player_ids: list[int]) -> None:
    """Set CSV export column order for this band layout."""
    now = _now()
    conn.execute(
        "UPDATE BandLayout SET export_column_order = ?, updated_at = ? WHERE id = ?",
        (json.dumps(player_ids), now, band_layout_id),
    )
    conn.commit()


def list_layout_slots_for_export(conn: sqlite3.Connection, band_layout_id: int) -> list[BandLayoutSlotRow]:
    """
    Return layout slots ordered for CSV export: by export_column_order if set,
    else by (y, x) row-major. Omits players no longer in layout; appends new players not in saved order.
    """
    slots = list_layout_slots(conn, band_layout_id)
    slot_by_player: dict[int, BandLayoutSlotRow] = {s.player_id: s for s in slots}
    saved_order = get_export_column_order(conn, band_layout_id)

    result: list[BandLayoutSlotRow] = []
    seen: set[int] = set()
    for pid in saved_order:
        if pid in slot_by_player and pid not in seen:
            result.append(slot_by_player[pid])
            seen.add(pid)
    for s in slots:
        if s.player_id not in seen:
            result.append(s)
    return result
