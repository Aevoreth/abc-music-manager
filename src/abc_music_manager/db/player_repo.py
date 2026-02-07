"""Player and PlayerInstrument CRUD. DATA_MODEL §4."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class PlayerRow:
    id: int
    name: str
    created_at: str
    updated_at: str


@dataclass
class PlayerInstrumentRow:
    id: int
    player_id: int
    instrument_id: int
    has_instrument: bool
    has_proficiency: bool
    notes: str | None
    created_at: str
    updated_at: str


def list_players(conn: sqlite3.Connection) -> list[PlayerRow]:
    cur = conn.execute("SELECT id, name, created_at, updated_at FROM Player ORDER BY name")
    return [PlayerRow(id=r[0], name=r[1], created_at=r[2], updated_at=r[3]) for r in cur.fetchall()]


def add_player(conn: sqlite3.Connection, name: str) -> int:
    now = _now()
    cur = conn.execute("INSERT INTO Player (name, created_at, updated_at) VALUES (?, ?, ?)", (name.strip(), now, now))
    conn.commit()
    return cur.lastrowid


def update_player(conn: sqlite3.Connection, player_id: int, name: str) -> None:
    conn.execute("UPDATE Player SET name = ?, updated_at = ? WHERE id = ?", (name.strip(), _now(), player_id))
    conn.commit()


def delete_player(conn: sqlite3.Connection, player_id: int) -> None:
    conn.execute("DELETE FROM PlayerInstrument WHERE player_id = ?", (player_id,))
    conn.execute("DELETE FROM BandLayoutSlot WHERE player_id = ?", (player_id,))
    conn.execute("DELETE FROM BandMember WHERE player_id = ?", (player_id,))
    conn.execute("DELETE FROM SongLayoutAssignment WHERE player_id = ?", (player_id,))
    conn.execute("DELETE FROM SetlistBandAssignment WHERE player_id = ?", (player_id,))
    conn.execute("DELETE FROM Player WHERE id = ?", (player_id,))
    conn.commit()


def list_player_instruments(conn: sqlite3.Connection, player_id: int) -> list[tuple[int, str, bool, bool]]:
    """Return (instrument_id, instrument_name, has_instrument, has_proficiency) for this player."""
    cur = conn.execute(
        """SELECT pi.instrument_id, i.name, pi.has_instrument, pi.has_proficiency
           FROM PlayerInstrument pi JOIN Instrument i ON i.id = pi.instrument_id
           WHERE pi.player_id = ? ORDER BY i.name""",
        (player_id,),
    )
    return [(r[0], r[1], bool(r[2]), bool(r[3])) for r in cur.fetchall()]


def set_player_instrument(
    conn: sqlite3.Connection,
    player_id: int,
    instrument_id: int,
    *,
    has_instrument: bool = True,
    has_proficiency: bool = False,
) -> None:
    now = _now()
    cur = conn.execute(
        "SELECT id FROM PlayerInstrument WHERE player_id = ? AND instrument_id = ?",
        (player_id, instrument_id),
    )
    row = cur.fetchone()
    if row:
        conn.execute(
            "UPDATE PlayerInstrument SET has_instrument = ?, has_proficiency = ?, updated_at = ? WHERE id = ?",
            (1 if has_instrument else 0, 1 if has_proficiency else 0, now, row[0]),
        )
    else:
        conn.execute(
            """INSERT INTO PlayerInstrument (player_id, instrument_id, has_instrument, has_proficiency, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (player_id, instrument_id, 1 if has_instrument else 0, 1 if has_proficiency else 0, now, now),
        )
    conn.commit()


def remove_player_instrument(conn: sqlite3.Connection, player_id: int, instrument_id: int) -> None:
    conn.execute("DELETE FROM PlayerInstrument WHERE player_id = ? AND instrument_id = ?", (player_id, instrument_id))
    conn.commit()
