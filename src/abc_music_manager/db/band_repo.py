"""Band, BandMember, BandLayout, BandLayoutSlot CRUD. DATA_MODEL §4."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class BandRow:
    id: int
    name: str
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
    cur = conn.execute("SELECT id, name, created_at, updated_at FROM Band ORDER BY name")
    return [BandRow(id=r[0], name=r[1], created_at=r[2], updated_at=r[3]) for r in cur.fetchall()]


def add_band(conn: sqlite3.Connection, name: str) -> int:
    now = _now()
    cur = conn.execute("INSERT INTO Band (name, created_at, updated_at) VALUES (?, ?, ?)", (name.strip(), now, now))
    conn.commit()
    return cur.lastrowid


def update_band(conn: sqlite3.Connection, band_id: int, name: str) -> None:
    conn.execute("UPDATE Band SET name = ?, updated_at = ? WHERE id = ?", (name.strip(), _now(), band_id))
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
    width_units: int = 7,
    height_units: int = 5,
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
