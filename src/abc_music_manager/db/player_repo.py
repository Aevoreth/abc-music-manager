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
    level: int | None
    class_: str | None
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


def list_players(
    conn: sqlite3.Connection,
    *,
    name_substring: str | None = None,
    level_min: int | None = None,
    level_max: int | None = None,
    class_substring: str | None = None,
    instrument_ids: list[int] | None = None,
) -> list[PlayerRow]:
    """List players sorted by name, with optional filters."""
    conditions: list[str] = []
    params: list[object] = []
    if name_substring and name_substring.strip():
        conditions.append("name LIKE ?")
        params.append(f"%{name_substring.strip()}%")
    if level_min is not None:
        conditions.append("(level IS NOT NULL AND level >= ?)")
        params.append(level_min)
    if level_max is not None:
        conditions.append("(level IS NOT NULL AND level <= ?)")
        params.append(level_max)
    if class_substring and class_substring.strip():
        conditions.append('"class" LIKE ?')
        params.append(f"%{class_substring.strip()}%")
    if instrument_ids:
        placeholders = ",".join("?" * len(instrument_ids))
        conditions.append(
            f"id IN (SELECT player_id FROM PlayerInstrument WHERE instrument_id IN ({placeholders}) AND has_instrument = 1)"
        )
        params.extend(instrument_ids)

    where = " AND ".join(conditions) if conditions else "1=1"
    sql = f'SELECT id, name, level, "class", created_at, updated_at FROM Player WHERE {where} ORDER BY name'
    cur = conn.execute(sql, params)
    return [
        PlayerRow(id=r[0], name=r[1], level=r[2], class_=r[3], created_at=r[4], updated_at=r[5])
        for r in cur.fetchall()
    ]


def add_player(
    conn: sqlite3.Connection,
    name: str,
    *,
    level: int | None = None,
    class_: str | None = None,
) -> int:
    now = _now()
    cur = conn.execute(
        'INSERT INTO Player (name, level, "class", created_at, updated_at) VALUES (?, ?, ?, ?, ?)',
        (name.strip(), level, class_.strip() if class_ and class_.strip() else None, now, now),
    )
    conn.commit()
    return cur.lastrowid


def update_player(
    conn: sqlite3.Connection,
    player_id: int,
    *,
    name: str,
    level: int | None = None,
    class_: str | None = None,
) -> None:
    """Update player name, level, and class. Level and class can be None to clear."""
    conn.execute(
        'UPDATE Player SET name = ?, level = ?, "class" = ?, updated_at = ? WHERE id = ?',
        (name.strip(), level, class_.strip() if class_ and class_.strip() else None, _now(), player_id),
    )
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


def list_player_instruments_bulk(
    conn: sqlite3.Connection, player_ids: list[int]
) -> dict[int, set[int]]:
    """Return {player_id: {instrument_id, ...}} for players who have has_instrument=1."""
    if not player_ids:
        return {}
    placeholders = ",".join("?" * len(player_ids))
    cur = conn.execute(
        f"""SELECT player_id, instrument_id FROM PlayerInstrument
           WHERE player_id IN ({placeholders}) AND has_instrument = 1""",
        player_ids,
    )
    result: dict[int, set[int]] = {pid: set() for pid in player_ids}
    for row in cur.fetchall():
        result[row[0]].add(row[1])
    return result


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
