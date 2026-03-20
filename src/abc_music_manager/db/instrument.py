"""
Instrument catalog: get by name/alternative_names or create. DATA_MODEL §1.
Used when parsing %%made-for from ABC parts.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# Spelling variants: ABC/LOTRO may use different spellings. Maps lowercase variant -> canonical name.
_INSTRUMENT_SPELLING_VARIANTS: dict[str, str] = {
    "traveller's trusty fiddle": "Traveler's Trusty Fiddle",
}


def resolve_instrument_id(conn: sqlite3.Connection, name: str) -> int:
    """
    Resolve instrument by name or alternative_names (comma-separated).
    If no match, create a new Instrument and return its id.
    """
    if not name or not name.strip():
        return _get_or_create_by_name(conn, "Unknown")
    return _get_or_create_by_name(conn, name.strip())


def _get_or_create_by_name(conn: sqlite3.Connection, name: str) -> int:
    """Find by name (exact, then case-insensitive) or by alternative_names; else insert new."""
    cur = conn.execute("SELECT id FROM Instrument WHERE name = ?", (name,))
    row = cur.fetchone()
    if row:
        return row[0]
    # Case-insensitive match (e.g. ABC "Jaunty Hand-knells" vs schema "Jaunty Hand-Knells")
    cur = conn.execute("SELECT id FROM Instrument WHERE LOWER(name) = LOWER(?)", (name,))
    row = cur.fetchone()
    if row:
        return row[0]
    # Spelling variant (e.g. "Traveller's Trusty Fiddle" vs "Traveler's Trusty Fiddle")
    canonical = _INSTRUMENT_SPELLING_VARIANTS.get(name.lower())
    if canonical:
        cur = conn.execute("SELECT id FROM Instrument WHERE LOWER(name) = LOWER(?)", (canonical,))
        row = cur.fetchone()
        if row:
            return row[0]
    cur = conn.execute("SELECT id, alternative_names FROM Instrument")
    for row in cur.fetchall():
        aid, alts = row[0], row[1]
        if alts:
            for alt in (a.strip() for a in alts.split(",")):
                if alt.lower() == name.lower():
                    return aid
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


def get_instrument_ids_with_same_name_ci(
    conn: sqlite3.Connection, instrument_id: int
) -> frozenset[int]:
    """
    Return all instrument IDs with the same name (case-insensitive) or spelling variant.
    Used when comparing part requirements to player instruments, since ABC parsing may have
    created duplicates (e.g. "Jaunty Hand-knells" vs "Jaunty Hand-Knells", "Traveller's" vs "Traveler's").
    """
    name = get_instrument_name(conn, instrument_id)
    if not name:
        return frozenset([instrument_id])
    # Collect equivalent names: this name + variants that map to/from it
    equiv_lower = {name.lower()}
    canonical = _INSTRUMENT_SPELLING_VARIANTS.get(name.lower(), name)
    equiv_lower.add(canonical.lower())
    for var, can in _INSTRUMENT_SPELLING_VARIANTS.items():
        if can.lower() == canonical.lower():
            equiv_lower.add(var)
    placeholders = ",".join("?" * len(equiv_lower))
    cur = conn.execute(
        f"SELECT id FROM Instrument WHERE LOWER(name) IN ({placeholders})",
        list(equiv_lower),
    )
    return frozenset(row[0] for row in cur.fetchall())


def list_instruments(conn: sqlite3.Connection) -> list[tuple[int, str]]:
    """Return (id, name) for all instruments, for dropdowns."""
    cur = conn.execute("SELECT id, name FROM Instrument ORDER BY name")
    return cur.fetchall()


def get_or_create_instruments_by_names(
    conn: sqlite3.Connection, names: list[str]
) -> dict[str, int]:
    """Return {name: instrument_id} for the given names, creating any that don't exist."""
    result: dict[str, int] = {}
    for name in names:
        if name and name.strip():
            result[name] = _get_or_create_by_name(conn, name.strip())
    return result
