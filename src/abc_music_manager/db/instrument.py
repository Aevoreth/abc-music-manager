"""
Instrument catalog: get by name/alternative_names or create. DATA_MODEL §1.
Used when parsing %%made-for from ABC parts.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def resolve_instrument_id(conn: sqlite3.Connection, name: str) -> int:
    """
    Resolve instrument by name or alternative_names (comma-separated).
    If no match, create a new Instrument and return its id.
    """
    if not name or not name.strip():
        # Return a sentinel or create "Unknown"? DATA_MODEL says instrument_id can be null in parts.
        # For simplicity we create an "Unknown" instrument if missing.
        return _get_or_create_by_name(conn, "Unknown")
    return _get_or_create_by_name(conn, name.strip())


def _get_or_create_by_name(conn: sqlite3.Connection, name: str) -> int:
    """Find by name (exact) or by alternative_names; else insert new."""
    cur = conn.execute("SELECT id FROM Instrument WHERE name = ?", (name,))
    row = cur.fetchone()
    if row:
        return row[0]
    # Check alternative_names (e.g. "Lute, lute, theorbos")
    cur = conn.execute("SELECT id, alternative_names FROM Instrument")
    for row in cur.fetchall():
        aid, alts = row[0], row[1]
        if alts:
            for alt in (a.strip() for a in alts.split(",")):
                if alt.lower() == name.lower():
                    return aid
    # Create new
    now = _now()
    cur = conn.execute(
        "INSERT INTO Instrument (name, alternative_names, created_at, updated_at) VALUES (?, NULL, ?, ?)",
        (name, now, now),
    )
    conn.commit()
    return cur.lastrowid


def get_instrument_name(conn: sqlite3.Connection, instrument_id: int) -> str | None:
    """Return primary display name for an instrument."""
    cur = conn.execute("SELECT name FROM Instrument WHERE id = ?", (instrument_id,))
    row = cur.fetchone()
    return row[0] if row else None
