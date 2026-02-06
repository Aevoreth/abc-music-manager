"""
Song and SongFile persistence: create/update from parser output and file metadata.
DATA_MODEL §1 (Song, SongFile). Logical identity = normalized title + composers + part count.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from ..abc_parser import ParsedSong
from .instrument import resolve_instrument_id


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_title(s: str) -> str:
    """Simple normalization for duplicate detection: strip, lower."""
    return (s or "").strip().lower()


def _parts_to_json(parsed: ParsedSong, conn: sqlite3.Connection) -> str:
    """Build parts JSON array with instrument_id resolved from made_for."""
    out = []
    for p in parsed.parts:
        instrument_id = None
        if p.made_for:
            instrument_id = resolve_instrument_id(conn, p.made_for)
        out.append({
            "part_number": p.part_number,
            "part_name": p.part_name,
            "instrument_id": instrument_id,
        })
    return json.dumps(out) if out else "[]"


def ensure_song_from_parsed(
    conn: sqlite3.Connection,
    parsed: ParsedSong,
    file_path: str,
    *,
    file_mtime: str | None = None,
    file_hash: str | None = None,
    is_primary_library: bool = True,
    is_set_copy: bool = False,
    scan_excluded: bool = False,
) -> int:
    """
    Create or update Song and SongFile for this path.
    If a SongFile with file_path exists, update it and its Song. Otherwise create new Song + SongFile.
    Returns song_id.
    """
    now = _now()
    parts_json = _parts_to_json(parsed, conn)

    cur = conn.execute("SELECT id, song_id FROM SongFile WHERE file_path = ?", (file_path,))
    existing = cur.fetchone()
    if existing:
        file_id, song_id = existing[0], existing[1]
        # Update Song
        conn.execute(
            """UPDATE Song SET title = ?, composers = ?, duration_seconds = ?, transcriber = ?,
               parts = ?, updated_at = ? WHERE id = ?""",
            (
                parsed.title,
                parsed.composers,
                parsed.duration_seconds,
                parsed.transcriber,
                parts_json,
                now,
                song_id,
            ),
        )
        # Update SongFile
        conn.execute(
            """UPDATE SongFile SET file_mtime = ?, file_hash = ?, export_timestamp = ?,
               is_primary_library = ?, is_set_copy = ?, scan_excluded = ?, updated_at = ? WHERE id = ?""",
            (
                file_mtime or None,
                file_hash,
                parsed.export_timestamp,
                1 if is_primary_library else 0,
                1 if is_set_copy else 0,
                1 if scan_excluded else 0,
                now,
                file_id,
            ),
        )
        conn.commit()
        return song_id

    # New file: create Song then SongFile
    cur = conn.execute(
        """INSERT INTO Song (title, composers, duration_seconds, transcriber, rating, status_id, notes, lyrics,
           last_played_at, total_plays, parts, created_at, updated_at)
           VALUES (?, ?, ?, ?, NULL, NULL, NULL, NULL, NULL, 0, ?, ?, ?)""",
        (parsed.title, parsed.composers, parsed.duration_seconds, parsed.transcriber, parts_json, now, now),
    )
    song_id = cur.lastrowid
    conn.execute(
        """INSERT INTO SongFile (song_id, file_path, file_mtime, file_hash, export_timestamp,
           is_primary_library, is_set_copy, scan_excluded, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            song_id,
            file_path,
            file_mtime,
            file_hash,
            parsed.export_timestamp,
            1 if is_primary_library else 0,
            1 if is_set_copy else 0,
            1 if scan_excluded else 0,
            now,
            now,
        ),
    )
    conn.commit()
    return song_id


def logical_identity(parsed: ParsedSong) -> tuple[str, str, int]:
    """Return (normalized_title, composers, part_count) for duplicate detection."""
    return (
        _normalize_title(parsed.title),
        (parsed.composers or "").strip(),
        len(parsed.parts),
    )


def find_song_by_logical_identity(
    conn: sqlite3.Connection,
    normalized_title: str,
    composers: str,
    part_count: int,
) -> list[int]:
    """Return list of song_ids that match this logical identity (for duplicate handling)."""
    cur = conn.execute(
        """SELECT id FROM Song WHERE LOWER(TRIM(title)) = ? AND TRIM(composers) = ? AND json_array_length(COALESCE(parts, '[]')) = ?""",
        (normalized_title, composers, part_count),
    )
    return [r[0] for r in cur.fetchall()]
