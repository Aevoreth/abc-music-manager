"""PlayLog: record a play and update Song.last_played_at / total_plays. DATA_MODEL §1."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def log_play(
    conn: sqlite3.Connection,
    song_id: int,
    *,
    context_setlist_id: int | None = None,
    context_note: str | None = None,
) -> None:
    """Insert a PlayLog row and refresh Song.last_played_at and total_plays."""
    now = _now()
    conn.execute(
        """INSERT INTO PlayLog (song_id, played_at, context_setlist_id, context_note, created_at)
           VALUES (?, ?, ?, ?, ?)""",
        (song_id, now, context_setlist_id, context_note, now),
    )
    conn.execute(
        """UPDATE Song SET last_played_at = (SELECT MAX(played_at) FROM PlayLog WHERE song_id = Song.id),
           total_plays = (SELECT COUNT(*) FROM PlayLog WHERE song_id = Song.id), updated_at = ? WHERE id = ?""",
        (now, song_id),
    )
    conn.commit()


def log_play_at(
    conn: sqlite3.Connection,
    song_id: int,
    played_at_iso: str,
    *,
    context_setlist_id: int | None = None,
    context_note: str | None = None,
) -> None:
    """Insert a PlayLog row with a specific played_at and refresh Song.last_played_at and total_plays."""
    conn.execute(
        """INSERT INTO PlayLog (song_id, played_at, context_setlist_id, context_note, created_at)
           VALUES (?, ?, ?, ?, ?)""",
        (song_id, played_at_iso, context_setlist_id, context_note, played_at_iso),
    )
    now = _now()
    conn.execute(
        """UPDATE Song SET last_played_at = (SELECT MAX(played_at) FROM PlayLog WHERE song_id = Song.id),
           total_plays = (SELECT COUNT(*) FROM PlayLog WHERE song_id = Song.id), updated_at = ? WHERE id = ?""",
        (now, song_id),
    )
    conn.commit()


def get_play_history(
    conn: sqlite3.Connection,
    song_id: int,
    *,
    limit: int = 500,
) -> list[tuple[int, str, str | None, str | None]]:
    """
    Return play history for a song: list of (play_log_id, played_at_iso, setlist_name, context_note).
    Most recent first.
    """
    cur = conn.execute(
        """SELECT pl.id, pl.played_at, sl.name, pl.context_note
           FROM PlayLog pl
           LEFT JOIN Setlist sl ON sl.id = pl.context_setlist_id
           WHERE pl.song_id = ?
           ORDER BY pl.played_at DESC
           LIMIT ?""",
        (song_id, limit),
    )
    return [(r[0], r[1], r[2], r[3]) for r in cur.fetchall()]


def update_play_log_entry(
    conn: sqlite3.Connection,
    play_log_id: int,
    *,
    played_at_iso: str,
    context_note: str | None = None,
) -> int | None:
    """
    Update a PlayLog entry. Returns song_id if updated, else None.
    Refreshes Song.last_played_at and total_plays for that song.
    """
    cur = conn.execute("SELECT song_id FROM PlayLog WHERE id = ?", (play_log_id,))
    row = cur.fetchone()
    if not row:
        return None
    song_id = row[0]
    conn.execute(
        """UPDATE PlayLog SET played_at = ?, context_note = ? WHERE id = ?""",
        (played_at_iso, context_note, play_log_id),
    )
    now = _now()
    conn.execute(
        """UPDATE Song SET last_played_at = (SELECT MAX(played_at) FROM PlayLog WHERE song_id = Song.id),
           total_plays = (SELECT COUNT(*) FROM PlayLog WHERE song_id = Song.id), updated_at = ? WHERE id = ?""",
        (now, song_id),
    )
    conn.commit()
    return song_id


def delete_play_log_entry(conn: sqlite3.Connection, play_log_id: int) -> int | None:
    """
    Delete a PlayLog entry. Returns song_id if deleted, else None.
    Refreshes Song.last_played_at and total_plays for that song.
    """
    cur = conn.execute("SELECT song_id FROM PlayLog WHERE id = ?", (play_log_id,))
    row = cur.fetchone()
    if not row:
        return None
    song_id = row[0]
    conn.execute("DELETE FROM PlayLog WHERE id = ?", (play_log_id,))
    now = _now()
    conn.execute(
        """UPDATE Song SET last_played_at = (SELECT MAX(played_at) FROM PlayLog WHERE song_id = Song.id),
           total_plays = (SELECT COUNT(*) FROM PlayLog WHERE song_id = Song.id), updated_at = ? WHERE id = ?""",
        (now, song_id),
    )
    conn.commit()
    return song_id
