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
