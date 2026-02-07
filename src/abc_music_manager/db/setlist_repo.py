"""Setlist and SetlistItem CRUD. DATA_MODEL §3."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class SetlistRow:
    id: int
    name: str
    band_layout_id: int | None
    locked: bool
    default_change_duration_seconds: int | None
    created_at: str
    updated_at: str


@dataclass
class SetlistItemRow:
    id: int
    setlist_id: int
    song_id: int
    position: int
    override_change_duration_seconds: int | None
    song_layout_id: int | None
    created_at: str
    updated_at: str


def list_setlists(conn: sqlite3.Connection) -> list[SetlistRow]:
    cur = conn.execute(
        """SELECT id, name, band_layout_id, locked, default_change_duration_seconds, created_at, updated_at
           FROM Setlist ORDER BY name"""
    )
    return [
        SetlistRow(
            id=r[0], name=r[1], band_layout_id=r[2], locked=bool(r[3]),
            default_change_duration_seconds=r[4], created_at=r[5], updated_at=r[6],
        )
        for r in cur.fetchall()
    ]


def get_setlists_containing_song(conn: sqlite3.Connection, song_id: int) -> list[tuple[int, str]]:
    """Return (setlist_id, setlist_name) for every setlist that contains this song."""
    cur = conn.execute(
        """SELECT sl.id, sl.name FROM Setlist sl
           JOIN SetlistItem si ON si.setlist_id = sl.id
           WHERE si.song_id = ? ORDER BY sl.name""",
        (song_id,),
    )
    return [(r[0], r[1]) for r in cur.fetchall()]


def add_setlist(conn: sqlite3.Connection, name: str) -> int:
    now = _now()
    cur = conn.execute(
        """INSERT INTO Setlist (name, band_layout_id, locked, default_change_duration_seconds, created_at, updated_at)
           VALUES (?, NULL, 0, NULL, ?, ?)""",
        (name.strip(), now, now),
    )
    conn.commit()
    return cur.lastrowid


def update_setlist(
    conn: sqlite3.Connection,
    setlist_id: int,
    *,
    name: str | None = None,
    band_layout_id: int | None = None,
    locked: bool | None = None,
    default_change_duration_seconds: int | None = None,
) -> None:
    updates = []
    args = []
    if name is not None:
        updates.append("name = ?")
        args.append(name.strip())
    if band_layout_id is not None:
        updates.append("band_layout_id = ?")
        args.append(band_layout_id)
    if locked is not None:
        updates.append("locked = ?")
        args.append(1 if locked else 0)
    if default_change_duration_seconds is not None:
        updates.append("default_change_duration_seconds = ?")
        args.append(default_change_duration_seconds)
    if not updates:
        return
    updates.append("updated_at = ?")
    args.append(_now())
    args.append(setlist_id)
    conn.execute(f"UPDATE Setlist SET {', '.join(updates)} WHERE id = ?", args)
    conn.commit()


def delete_setlist(conn: sqlite3.Connection, setlist_id: int) -> None:
    conn.execute("DELETE FROM SetlistBandAssignment WHERE setlist_item_id IN (SELECT id FROM SetlistItem WHERE setlist_id = ?)", (setlist_id,))
    conn.execute("DELETE FROM SetlistItem WHERE setlist_id = ?", (setlist_id,))
    conn.execute("DELETE FROM Setlist WHERE id = ?", (setlist_id,))
    conn.commit()


def list_setlist_items(conn: sqlite3.Connection, setlist_id: int) -> list[tuple[SetlistItemRow, str]]:
    """Return (SetlistItemRow, song_title) for each item, ordered by position."""
    cur = conn.execute(
        """SELECT si.id, si.setlist_id, si.song_id, si.position, si.override_change_duration_seconds, si.song_layout_id, si.created_at, si.updated_at, s.title
           FROM SetlistItem si JOIN Song s ON s.id = si.song_id
           WHERE si.setlist_id = ? ORDER BY si.position""",
        (setlist_id,),
    )
    return [
        (
            SetlistItemRow(
                id=r[0], setlist_id=r[1], song_id=r[2], position=r[3],
                override_change_duration_seconds=r[4], song_layout_id=r[5], created_at=r[6], updated_at=r[7],
            ),
            r[8],
        )
        for r in cur.fetchall()
    ]


def add_setlist_item(
    conn: sqlite3.Connection,
    setlist_id: int,
    song_id: int,
    position: int,
    song_layout_id: int | None = None,
    override_change_duration_seconds: int | None = None,
) -> int:
    now = _now()
    cur = conn.execute(
        """INSERT INTO SetlistItem (setlist_id, song_id, position, override_change_duration_seconds, song_layout_id, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (setlist_id, song_id, position, override_change_duration_seconds, song_layout_id, now, now),
    )
    conn.commit()
    return cur.lastrowid


def update_setlist_item_position(conn: sqlite3.Connection, item_id: int, position: int) -> None:
    conn.execute("UPDATE SetlistItem SET position = ?, updated_at = ? WHERE id = ?", (position, _now(), item_id))
    conn.commit()


def update_setlist_item(
    conn: sqlite3.Connection,
    item_id: int,
    *,
    song_layout_id: int | None = None,
    override_change_duration_seconds: int | None = None,
) -> None:
    updates = []
    args = []
    if song_layout_id is not None:
        updates.append("song_layout_id = ?")
        args.append(song_layout_id)
    if override_change_duration_seconds is not None:
        updates.append("override_change_duration_seconds = ?")
        args.append(override_change_duration_seconds)
    if not updates:
        return
    updates.append("updated_at = ?")
    args.append(_now())
    args.append(item_id)
    conn.execute(f"UPDATE SetlistItem SET {', '.join(updates)} WHERE id = ?", args)
    conn.commit()


def remove_setlist_item(conn: sqlite3.Connection, item_id: int) -> None:
    conn.execute("DELETE FROM SetlistBandAssignment WHERE setlist_item_id = ?", (item_id,))
    conn.execute("DELETE FROM SetlistItem WHERE id = ?", (item_id,))
    conn.commit()
    # Reorder positions
    # (caller may pass setlist_id to renumber; for simplicity we leave positions as-is and rely on ORDER BY position)


def reorder_setlist_items(conn: sqlite3.Connection, setlist_id: int, item_ids_in_order: list[int]) -> None:
    """Set position 0,1,2,... for the given item ids in order."""
    now = _now()
    for pos, item_id in enumerate(item_ids_in_order):
        conn.execute("UPDATE SetlistItem SET position = ?, updated_at = ? WHERE id = ? AND setlist_id = ?", (pos, now, item_id, setlist_id))
    conn.commit()
