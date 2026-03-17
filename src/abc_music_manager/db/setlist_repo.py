"""Setlist and SetlistItem CRUD. DATA_MODEL §3."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


_UNSET: Any = object()


@dataclass
class SetlistRow:
    id: int
    name: str
    band_layout_id: int | None
    locked: bool
    default_change_duration_seconds: int | None
    notes: str | None
    set_date: str | None
    set_time: str | None
    target_duration_seconds: int | None
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


@dataclass
class SetlistItemSongMetaRow:
    """SetlistItem joined with Song fields for the setlist editor table."""

    item: SetlistItemRow
    title: str
    composers: str
    duration_seconds: int | None
    part_count: int
    parts_json: str | None


def list_setlists(conn: sqlite3.Connection) -> list[SetlistRow]:
    cur = conn.execute(
        """SELECT id, name, band_layout_id, locked, default_change_duration_seconds,
                  COALESCE(notes, ''), set_date, set_time, target_duration_seconds,
                  created_at, updated_at
           FROM Setlist ORDER BY name"""
    )
    return [
        SetlistRow(
            id=r[0],
            name=r[1],
            band_layout_id=r[2],
            locked=bool(r[3]),
            default_change_duration_seconds=r[4],
            notes=r[5] if r[5] else None,
            set_date=r[6] if r[6] else None,
            set_time=r[7] if r[7] else None,
            target_duration_seconds=r[8],
            created_at=r[9],
            updated_at=r[10],
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
    from datetime import date
    now = _now()
    today = date.today().isoformat()
    default_time = "19:00"
    cur = conn.execute(
        """INSERT INTO Setlist (name, band_layout_id, locked, default_change_duration_seconds, notes,
                  set_date, set_time, target_duration_seconds, created_at, updated_at)
           VALUES (?, NULL, 0, NULL, NULL, ?, ?, NULL, ?, ?)""",
        (name.strip(), today, default_time, now, now),
    )
    conn.commit()
    return cur.lastrowid


def update_setlist(
    conn: sqlite3.Connection,
    setlist_id: int,
    *,
    name: str | None = None,
    band_layout_id: Any = _UNSET,
    locked: bool | None = None,
    default_change_duration_seconds: Any = _UNSET,
    notes: Any = _UNSET,
    set_date: Any = _UNSET,
    set_time: Any = _UNSET,
    target_duration_seconds: Any = _UNSET,
) -> None:
    updates = []
    args = []
    if name is not None:
        updates.append("name = ?")
        args.append(name.strip())
    if band_layout_id is not _UNSET:
        updates.append("band_layout_id = ?")
        args.append(band_layout_id)
    if locked is not None:
        updates.append("locked = ?")
        args.append(1 if locked else 0)
    if default_change_duration_seconds is not _UNSET:
        updates.append("default_change_duration_seconds = ?")
        args.append(default_change_duration_seconds)
    if notes is not _UNSET:
        updates.append("notes = ?")
        args.append(notes if notes else None)
    if set_date is not _UNSET:
        updates.append("set_date = ?")
        args.append(set_date if set_date else None)
    if set_time is not _UNSET:
        updates.append("set_time = ?")
        args.append(set_time if set_time else None)
    if target_duration_seconds is not _UNSET:
        updates.append("target_duration_seconds = ?")
        args.append(target_duration_seconds)
    if not updates:
        return
    updates.append("updated_at = ?")
    args.append(_now())
    args.append(setlist_id)
    conn.execute(f"UPDATE Setlist SET {', '.join(updates)} WHERE id = ?", args)
    conn.commit()


def delete_setlist(conn: sqlite3.Connection, setlist_id: int) -> None:
    conn.execute(
        "DELETE FROM SetlistBandAssignment WHERE setlist_item_id IN (SELECT id FROM SetlistItem WHERE setlist_id = ?)",
        (setlist_id,),
    )
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
                id=r[0],
                setlist_id=r[1],
                song_id=r[2],
                position=r[3],
                override_change_duration_seconds=r[4],
                song_layout_id=r[5],
                created_at=r[6],
                updated_at=r[7],
            ),
            r[8],
        )
        for r in cur.fetchall()
    ]


def list_setlist_items_with_song_meta(conn: sqlite3.Connection, setlist_id: int) -> list[SetlistItemSongMetaRow]:
    """Setlist items with song title, composers, duration, part count, parts JSON."""
    cur = conn.execute(
        """SELECT si.id, si.setlist_id, si.song_id, si.position, si.override_change_duration_seconds,
                  si.song_layout_id, si.created_at, si.updated_at,
                  s.title, s.composers, s.duration_seconds,
                  json_array_length(COALESCE(s.parts, '[]')), s.parts
           FROM SetlistItem si JOIN Song s ON s.id = si.song_id
           WHERE si.setlist_id = ? ORDER BY si.position""",
        (setlist_id,),
    )
    rows = []
    for r in cur.fetchall():
        item = SetlistItemRow(
            id=r[0],
            setlist_id=r[1],
            song_id=r[2],
            position=r[3],
            override_change_duration_seconds=r[4],
            song_layout_id=r[5],
            created_at=r[6],
            updated_at=r[7],
        )
        rows.append(
            SetlistItemSongMetaRow(
                item=item,
                title=r[8],
                composers=r[9] or "",
                duration_seconds=r[10],
                part_count=int(r[11] or 0),
                parts_json=r[12],
            )
        )
    return rows


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
    song_layout_id: Any = _UNSET,
    override_change_duration_seconds: Any = _UNSET,
) -> None:
    updates = []
    args = []
    if song_layout_id is not _UNSET:
        updates.append("song_layout_id = ?")
        args.append(song_layout_id)
    if override_change_duration_seconds is not _UNSET:
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


def reorder_setlist_items(conn: sqlite3.Connection, setlist_id: int, item_ids_in_order: list[int]) -> None:
    """Set position 0,1,2,... for the given item ids in order."""
    now = _now()
    for pos, item_id in enumerate(item_ids_in_order):
        conn.execute(
            "UPDATE SetlistItem SET position = ?, updated_at = ? WHERE id = ? AND setlist_id = ?",
            (pos, now, item_id, setlist_id),
        )
    conn.commit()


# --- SetlistBandAssignment (per-setlist-item player -> part overrides) ---


def get_setlist_band_assignments(conn: sqlite3.Connection, setlist_item_id: int) -> dict[int, int | None]:
    """Return {player_id: part_number or None} for explicit override rows."""
    cur = conn.execute(
        "SELECT player_id, part_number FROM SetlistBandAssignment WHERE setlist_item_id = ?",
        (setlist_item_id,),
    )
    return {r[0]: r[1] for r in cur.fetchall()}


def upsert_setlist_band_assignment(
    conn: sqlite3.Connection,
    setlist_item_id: int,
    player_id: int,
    part_number: int | None,
) -> None:
    """Insert or update override for (setlist_item, player). part_number None = no part."""
    now = _now()
    cur = conn.execute(
        "SELECT id FROM SetlistBandAssignment WHERE setlist_item_id = ? AND player_id = ?",
        (setlist_item_id, player_id),
    )
    row = cur.fetchone()
    if row:
        conn.execute(
            "UPDATE SetlistBandAssignment SET part_number = ?, updated_at = ? WHERE id = ?",
            (part_number, now, row[0]),
        )
    else:
        conn.execute(
            """INSERT INTO SetlistBandAssignment (setlist_item_id, player_id, part_number, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?)""",
            (setlist_item_id, player_id, part_number, now, now),
        )
    conn.commit()


def delete_setlist_band_assignment(conn: sqlite3.Connection, setlist_item_id: int, player_id: int) -> None:
    """Remove override row so SongLayoutAssignment applies again for this player."""
    conn.execute(
        "DELETE FROM SetlistBandAssignment WHERE setlist_item_id = ? AND player_id = ?",
        (setlist_item_id, player_id),
    )
    conn.commit()
