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
) -> list[tuple[str, str | None, str | None]]:
    """
    Return play history for a song: list of (played_at_iso, setlist_name, context_note).
    Most recent first.
    """
    cur = conn.execute(
        """SELECT pl.played_at, pl.context_note, sl.name
           FROM PlayLog pl
           LEFT JOIN Setlist sl ON sl.id = pl.context_setlist_id
           WHERE pl.song_id = ?
           ORDER BY pl.played_at DESC
           LIMIT ?""",
        (song_id, limit),
    )
    return [(r[0], r[2], r[1]) for r in cur.fetchall()]
