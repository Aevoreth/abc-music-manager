"""SongLayout and SongLayoutAssignment CRUD. DATA_MODEL §2."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class SongLayoutRow:
    id: int
    song_id: int
    band_layout_id: int
    name: str | None
    created_at: str
    updated_at: str


@dataclass
class SongLayoutAssignmentRow:
    song_layout_id: int
    player_id: int
    part_number: int | None


def list_song_layouts_for_song(conn: sqlite3.Connection, song_id: int) -> list[tuple[SongLayoutRow, str]]:
    """Return (SongLayoutRow, band_layout_name) for this song."""
    cur = conn.execute(
        """SELECT sl.id, sl.song_id, sl.band_layout_id, sl.name, sl.created_at, sl.updated_at, bl.name AS bl_name
           FROM SongLayout sl JOIN BandLayout bl ON bl.id = sl.band_layout_id
           WHERE sl.song_id = ? ORDER BY bl.name, sl.name""",
        (song_id,),
    )
    return [
        (
            SongLayoutRow(id=r[0], song_id=r[1], band_layout_id=r[2], name=r[3], created_at=r[4], updated_at=r[5]),
            r[6],
        )
        for r in cur.fetchall()
    ]


def list_song_layouts_for_song_and_band(conn: sqlite3.Connection, song_id: int, band_layout_id: int) -> list[SongLayoutRow]:
    """Return SongLayoutRows for this song and band layout (for setlist item picker)."""
    cur = conn.execute(
        "SELECT id, song_id, band_layout_id, name, created_at, updated_at FROM SongLayout WHERE song_id = ? AND band_layout_id = ? ORDER BY name",
        (song_id, band_layout_id),
    )
    return [SongLayoutRow(id=r[0], song_id=r[1], band_layout_id=r[2], name=r[3], created_at=r[4], updated_at=r[5]) for r in cur.fetchall()]


def add_song_layout(conn: sqlite3.Connection, song_id: int, band_layout_id: int, name: str | None = None) -> int:
    now = _now()
    cur = conn.execute(
        """INSERT INTO SongLayout (song_id, band_layout_id, name, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?)""",
        (song_id, band_layout_id, name.strip() if name else None, now, now),
    )
    conn.commit()
    return cur.lastrowid


def set_song_layout_assignment(conn: sqlite3.Connection, song_layout_id: int, player_id: int, part_number: int | None) -> None:
    now = _now()
    cur = conn.execute(
        "SELECT id FROM SongLayoutAssignment WHERE song_layout_id = ? AND player_id = ?",
        (song_layout_id, player_id),
    )
    row = cur.fetchone()
    if row:
        conn.execute(
            "UPDATE SongLayoutAssignment SET part_number = ?, updated_at = ? WHERE id = ?",
            (part_number, now, row[0]),
        )
    else:
        conn.execute(
            """INSERT INTO SongLayoutAssignment (song_layout_id, player_id, part_number, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?)""",
            (song_layout_id, player_id, part_number, now, now),
        )
    conn.commit()


def get_song_layout_assignments(conn: sqlite3.Connection, song_layout_id: int) -> list[SongLayoutAssignmentRow]:
    cur = conn.execute(
        "SELECT song_layout_id, player_id, part_number FROM SongLayoutAssignment WHERE song_layout_id = ?",
        (song_layout_id,),
    )
    return [SongLayoutAssignmentRow(song_layout_id=r[0], player_id=r[1], part_number=r[2]) for r in cur.fetchall()]


def delete_song_layout(conn: sqlite3.Connection, song_layout_id: int) -> None:
    conn.execute("DELETE FROM SongLayoutAssignment WHERE song_layout_id = ?", (song_layout_id,))
    conn.execute("DELETE FROM SongLayout WHERE id = ?", (song_layout_id,))
    conn.commit()
