"""Remove SongFile rows and cascade-delete songs that no longer have files."""

from __future__ import annotations

import sqlite3


def cleanup_orphaned_songs_after_songfile_deletion(conn: sqlite3.Connection) -> None:
    """
    After SongFile rows were removed, delete dependent rows and orphaned Song records.
    Matches cascade logic used at end of library scan.
    """
    orphan_item_ids = (
        "SELECT id FROM SetlistItem WHERE song_id NOT IN (SELECT song_id FROM SongFile WHERE song_id IS NOT NULL)"
    )
    conn.execute(
        f"UPDATE Song SET last_setlist_item_id = NULL WHERE last_setlist_item_id IN ({orphan_item_ids})"
    )
    conn.execute(
        f"""DELETE FROM SetlistBandAssignment WHERE setlist_item_id IN ({orphan_item_ids})"""
    )
    conn.execute(
        """DELETE FROM SetlistItem WHERE song_id NOT IN (SELECT song_id FROM SongFile WHERE song_id IS NOT NULL)"""
    )
    conn.execute(
        """DELETE FROM SongLayoutAssignment WHERE song_layout_id IN
           (SELECT id FROM SongLayout WHERE song_id NOT IN (SELECT song_id FROM SongFile WHERE song_id IS NOT NULL))"""
    )
    conn.execute(
        """DELETE FROM SongLayout WHERE song_id NOT IN (SELECT song_id FROM SongFile WHERE song_id IS NOT NULL)"""
    )
    conn.execute(
        """DELETE FROM PlayLog WHERE song_id NOT IN (SELECT song_id FROM SongFile WHERE song_id IS NOT NULL)"""
    )
    conn.execute(
        """DELETE FROM Song WHERE id NOT IN (SELECT song_id FROM SongFile WHERE song_id IS NOT NULL)"""
    )
    conn.commit()


def delete_songfiles_for_paths(conn: sqlite3.Connection, file_paths: list[str]) -> None:
    """Delete SongFile rows for exact paths, then orphan cleanup."""
    if not file_paths:
        return
    conn.executemany("DELETE FROM SongFile WHERE file_path = ?", [(p,) for p in file_paths])
    cleanup_orphaned_songs_after_songfile_deletion(conn)
