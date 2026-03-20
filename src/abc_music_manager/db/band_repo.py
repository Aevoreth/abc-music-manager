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
    cur = conn.execute("SELECT id, name, created_at, updated_at, notes FROM Band ORDER BY name")
    return [BandRow(id=r[0], name=r[1], notes=r[4], created_at=r[2], updated_at=r[3]) for r in cur.fetchall()]


def add_band(conn: sqlite3.Connection, name: str, notes: str | None = None) -> int:
    now = _now()
    cur = conn.execute(
        "INSERT INTO Band (name, notes, created_at, updated_at) VALUES (?, ?, ?, ?)",
        (name.strip(), notes or None, now, now),
    )
    conn.commit()
    return cur.lastrowid


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
        """SELECT bl.id, bl.name, b.name FROM BandLayout bl JOIN Band b ON b.id = bl.band_id ORDER BY b.name, bl.name"""
    )
    return [(r[0], r[1], r[2]) for r in cur.fetchall()]


def get_band_layout_display_name(conn: sqlite3.Connection, band_layout_id: int | None) -> str:
    """Return display string for band layout (e.g. 'Band Name — Layout Name'). Returns '(draft)' if None."""
    if band_layout_id is None:
        return "(draft)"
    for lid, layout_name, band_name in list_all_band_layouts(conn):
        if lid == band_layout_id:
            return f"{band_name} — {layout_name}"
    return "(unknown)"


def list_band_layouts(conn: sqlite3.Connection, band_id: int) -> list[BandLayoutRow]:
    cur = conn.execute(
        "SELECT id, band_id, name, created_at, updated_at FROM BandLayout WHERE band_id = ? ORDER BY name",
        (band_id,),
    )
    return [BandLayoutRow(id=r[0], band_id=r[1], name=r[2], created_at=r[3], updated_at=r[4]) for r in cur.fetchall()]


def add_band_layout(conn: sqlite3.Connection, band_id: int, name: str) -> int:
    now = _now()
    cur = conn.execute(
        "INSERT INTO BandLayout (band_id, name, created_at, updated_at) VALUES (?, ?, ?, ?)",
        (band_id, name.strip(), now, now),
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
