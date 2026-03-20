"""SetlistFolder CRUD for setlist categories."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class SetlistFolderRow:
    id: int
    name: str
    sort_order: int
    created_at: str
    updated_at: str


def list_folders(conn: sqlite3.Connection) -> list[SetlistFolderRow]:
    """Return all folders ordered by sort_order, then name."""
    cur = conn.execute(
        """SELECT id, name, sort_order, created_at, updated_at
           FROM SetlistFolder ORDER BY sort_order, name"""
    )
    return [
        SetlistFolderRow(
            id=r[0],
            name=r[1],
            sort_order=r[2],
            created_at=r[3],
            updated_at=r[4],
        )
        for r in cur.fetchall()
    ]


def add_folder(conn: sqlite3.Connection, name: str) -> int:
    """Create a new folder. sort_order = max+1. Returns new id."""
    cur = conn.execute("SELECT COALESCE(MAX(sort_order), -1) + 1 FROM SetlistFolder")
    next_order = cur.fetchone()[0]
    now = _now()
    cur = conn.execute(
        """INSERT INTO SetlistFolder (name, sort_order, created_at, updated_at)
           VALUES (?, ?, ?, ?)""",
        (name.strip(), next_order, now, now),
    )
    conn.commit()
    return cur.lastrowid


def update_folder(
    conn: sqlite3.Connection,
    folder_id: int,
    *,
    name: str | None = None,
    sort_order: int | None = None,
) -> None:
    """Update folder name and/or sort_order."""
    updates = []
    args = []
    if name is not None:
        updates.append("name = ?")
        args.append(name.strip())
    if sort_order is not None:
        updates.append("sort_order = ?")
        args.append(sort_order)
    if not updates:
        return
    updates.append("updated_at = ?")
    args.append(_now())
    args.append(folder_id)
    conn.execute(f"UPDATE SetlistFolder SET {', '.join(updates)} WHERE id = ?", args)
    conn.commit()


def delete_folder(conn: sqlite3.Connection, folder_id: int) -> None:
    """Delete folder only if it has no setlists. Raises ValueError if not empty."""
    cur = conn.execute("SELECT COUNT(*) FROM Setlist WHERE folder_id = ?", (folder_id,))
    if cur.fetchone()[0] > 0:
        raise ValueError("Cannot delete folder: it contains setlists")
    conn.execute("DELETE FROM SetlistFolder WHERE id = ?", (folder_id,))
    conn.commit()


def reorder_folders(conn: sqlite3.Connection, folder_ids_in_order: list[int]) -> None:
    """Set sort_order 0, 1, 2, ... for the given folder ids."""
    now = _now()
    for pos, fid in enumerate(folder_ids_in_order):
        conn.execute(
            "UPDATE SetlistFolder SET sort_order = ?, updated_at = ? WHERE id = ?",
            (pos, now, fid),
        )
    conn.commit()
