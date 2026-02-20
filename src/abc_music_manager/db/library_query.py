"""
Library view query: songs to show in main library (primary, not set copies, not excluded).
REQUIREMENTS §1, DECISIONS 020.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import Optional
from .instrument import get_instrument_name


@dataclass
class LibrarySongRow:
    song_id: int
    title: str
    composers: str
    transcriber: Optional[str]
    duration_seconds: Optional[int]
    part_count: int
    parts_json: Optional[str]  # JSON array for tooltip (part names)
    last_played_at: Optional[str]
    total_plays: int
    rating: Optional[int]
    status_id: Optional[int]
    status_name: Optional[str]
    status_color: Optional[str]
    notes: Optional[str]
    lyrics: Optional[str]
    in_upcoming_set: bool


def list_library_songs(
    conn: sqlite3.Connection,
    *,
    title_substring: Optional[str] = None,
    composer_substring: Optional[str] = None,
    transcriber_substring: Optional[str] = None,
    duration_min_sec: Optional[int] = None,
    duration_max_sec: Optional[int] = None,
    rating_min: Optional[int] = None,
    rating_max: Optional[int] = None,
    status_ids: Optional[list[int]] = None,
    part_count_min: Optional[int] = None,
    part_count_max: Optional[int] = None,
    plays_in_last_n_days: Optional[int] = None,
    limit: int = 2000,
) -> list[LibrarySongRow]:
    """
    Return songs for main library view (has at least one primary, non-excluded SongFile).
    Set copies are excluded (DECISIONS 020). Optional filters applied.
    """
    main_library = """
        SELECT DISTINCT song_id FROM SongFile
        WHERE is_primary_library = 1 AND scan_excluded = 0
    """
    conditions = ["s.id IN (" + main_library + ")"]
    args = []

    if title_substring:
        conditions.append("LOWER(s.title) LIKE ?")
        args.append("%" + title_substring.lower() + "%")
    if composer_substring:
        conditions.append("LOWER(s.composers) LIKE ?")
        args.append("%" + composer_substring.lower() + "%")
    if transcriber_substring:
        conditions.append("(s.transcriber IS NOT NULL AND LOWER(s.transcriber) LIKE ?)")
        args.append("%" + transcriber_substring.lower() + "%")
    if duration_min_sec is not None:
        conditions.append("s.duration_seconds >= ?")
        args.append(duration_min_sec)
    if duration_max_sec is not None:
        conditions.append("s.duration_seconds <= ?")
        args.append(duration_max_sec)
    if rating_min is not None:
        conditions.append("(s.rating IS NOT NULL AND s.rating >= ?)")
        args.append(rating_min)
    if rating_max is not None:
        conditions.append("(s.rating IS NOT NULL AND s.rating <= ?)")
        args.append(rating_max)
    if status_ids:
        placeholders = ",".join("?" * len(status_ids))
        conditions.append(f"s.status_id IN ({placeholders})")
        args.extend(status_ids)
    if part_count_min is not None:
        conditions.append("json_array_length(COALESCE(s.parts, '[]')) >= ?")
        args.append(part_count_min)
    if part_count_max is not None:
        conditions.append("json_array_length(COALESCE(s.parts, '[]')) <= ?")
        args.append(part_count_max)
    if plays_in_last_n_days is not None and plays_in_last_n_days > 0:
        conditions.append("""EXISTS (
            SELECT 1 FROM PlayLog pl WHERE pl.song_id = s.id
            AND pl.played_at >= datetime('now', ?)
        )""")
        args.append(f"-{plays_in_last_n_days} days")

    where = " AND ".join(conditions)
    args.append(limit)

    sql = f"""
        SELECT s.id, s.title, s.composers, s.transcriber, s.duration_seconds,
               json_array_length(COALESCE(s.parts, '[]')) AS part_count,
               s.parts,
               s.last_played_at, s.total_plays, s.rating, s.status_id,
               st.name AS status_name, st.color AS status_color,
               s.notes, s.lyrics,
               EXISTS (SELECT 1 FROM SetlistItem si JOIN Setlist sl ON sl.id = si.setlist_id WHERE si.song_id = s.id AND sl.locked = 0) AS in_upcoming_set
        FROM Song s
        LEFT JOIN Status st ON st.id = s.status_id
        WHERE {where}
        ORDER BY s.title
        LIMIT ?
    """
    cur = conn.execute(sql, args)
    return [
        LibrarySongRow(
            song_id=r[0],
            title=r[1],
            composers=r[2],
            transcriber=r[3],
            duration_seconds=r[4],
            part_count=r[5] or 0,
            parts_json=r[6],
            last_played_at=r[7],
            total_plays=r[8] or 0,
            rating=r[9],
            status_id=r[10],
            status_name=r[11],
            status_color=r[12],
            notes=r[13],
            lyrics=r[14],
            in_upcoming_set=bool(r[15]),
        )
        for r in cur.fetchall()
    ]


def get_status_list(conn: sqlite3.Connection) -> list[tuple[int, str]]:
    """Return (id, name) for all statuses for filter dropdown (ordered by sort_order)."""
    cur = conn.execute("SELECT id, name FROM Status ORDER BY sort_order, name")
    return cur.fetchall()


def get_song_for_detail(conn: sqlite3.Connection, song_id: int) -> Optional[dict]:
    """
    Return song row as dict for Song Detail view: id, title, composers, transcriber,
    duration_seconds, part_count, parts (list of {part_number, part_name, instrument_name}),
    status_name, rating, notes, lyrics. Returns None if not found.
    """
    cur = conn.execute(
        """SELECT s.id, s.title, s.composers, s.transcriber, s.duration_seconds, s.parts,
                  s.rating, s.status_id, s.notes, s.lyrics, st.name AS status_name,
                  (SELECT export_timestamp FROM SongFile WHERE song_id = s.id LIMIT 1) AS export_timestamp
           FROM Song s LEFT JOIN Status st ON st.id = s.status_id WHERE s.id = ?""",
        (song_id,),
    )
    row = cur.fetchone()
    if not row:
        return None
    parts_json = row[5]
    parts_list = json.loads(parts_json) if parts_json else []
    for p in parts_list:
        iid = p.get("instrument_id")
        p["instrument_name"] = get_instrument_name(conn, iid) if iid else None
    return {
        "id": row[0],
        "title": row[1],
        "composers": row[2],
        "transcriber": row[3],
        "duration_seconds": row[4],
        "part_count": len(parts_list),
        "parts": parts_list,
        "rating": row[6],
        "status_id": row[7],
        "notes": row[8],
        "lyrics": row[9],
        "status_name": row[10],
        "export_timestamp": row[11],
    }


def get_primary_file_path_for_song(conn: sqlite3.Connection, song_id: int) -> Optional[str]:
    """Return a primary-library file path for this song (for raw ABC read/write). Prefer is_primary_library=1."""
    cur = conn.execute(
        """SELECT file_path FROM SongFile WHERE song_id = ? AND is_primary_library = 1 AND scan_excluded = 0
           LIMIT 1""",
        (song_id,),
    )
    row = cur.fetchone()
    if row:
        return row[0]
    cur = conn.execute("SELECT file_path FROM SongFile WHERE song_id = ? LIMIT 1", (song_id,))
    row = cur.fetchone()
    return row[0] if row else None


def get_title_composers_for_file_path(conn: sqlite3.Connection, file_path: str) -> Optional[tuple[str, str]]:
    """Return (title, composers) for a file path if it exists in SongFile, else None."""
    cur = conn.execute(
        "SELECT s.title, s.composers FROM Song s JOIN SongFile f ON f.song_id = s.id WHERE f.file_path = ? LIMIT 1",
        (file_path,),
    )
    row = cur.fetchone()
    return (row[0], row[1]) if row else None
