"""Status CRUD. DATA_MODEL §1 (Status)."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class StatusRow:
    id: int
    name: str
    color: str | None
    sort_order: int | None
    created_at: str
    updated_at: str


def list_statuses(conn: sqlite3.Connection) -> list[StatusRow]:
    cur = conn.execute(
        "SELECT id, name, color, sort_order, created_at, updated_at FROM Status ORDER BY sort_order, name"
    )
    return [
        StatusRow(
            id=r[0],
            name=r[1],
            color=r[2],
            sort_order=r[3],
            created_at=r[4],
            updated_at=r[5],
        )
        for r in cur.fetchall()
    ]


def get_effective_default_status_id(conn: sqlite3.Connection) -> int | None:
    """Default status id for new songs / library. Uses preference, or first status (New) if unset."""
    from ..services.preferences import get_default_status_id
    default_id = get_default_status_id()
    if default_id is not None:
        return default_id
    statuses = list_statuses(conn)
    return statuses[0].id if statuses else None


def add_status(
    conn: sqlite3.Connection,
    name: str,
    *,
    color: str | None = None,
    sort_order: int | None = None,
) -> int:
    now = _now()
    cur = conn.execute(
        """INSERT INTO Status (name, color, sort_order, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?)""",
        (name.strip(), color, sort_order, now, now),
    )
    conn.commit()
    return cur.lastrowid


def update_status(
    conn: sqlite3.Connection,
    status_id: int,
    *,
    name: str | None = None,
    color: str | None = None,
    sort_order: int | None = None,
) -> None:
    updates = []
    args = []
    if name is not None:
        updates.append("name = ?")
        args.append(name.strip())
    if color is not None:
        updates.append("color = ?")
        args.append(color)
    if sort_order is not None:
        updates.append("sort_order = ?")
        args.append(sort_order)
    if not updates:
        return
    updates.append("updated_at = ?")
    args.append(_now())
    args.append(status_id)
    conn.execute(f"UPDATE Status SET {', '.join(updates)} WHERE id = ?", args)
    conn.commit()


def reorder_statuses(conn: sqlite3.Connection, id_order: list[int]) -> None:
    """Set sort_order by list position (0-based). id_order lists status ids in desired order."""
    now = _now()
    for i, sid in enumerate(id_order):
        conn.execute("UPDATE Status SET sort_order = ?, updated_at = ? WHERE id = ?", (i, now, sid))
    conn.commit()


def delete_status(conn: sqlite3.Connection, status_id: int) -> None:
    conn.execute("UPDATE Song SET status_id = NULL WHERE status_id = ?", (status_id,))
    conn.execute("DELETE FROM Status WHERE id = ?", (status_id,))
    conn.commit()
