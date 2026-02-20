"""
Filesystem scanner: discover .abc files under FolderRule roots, parse and index.
REQUIREMENTS §3, DECISIONS 019, 020. Does not implement duplicate-resolution UI (creates separate songs on collision for now).
"""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path
from typing import Callable

from ..parsing.abc_parser import parse_abc_file, ParsedSong
from ..db.folder_rule import get_enabled_roots
from ..db.song_repo import (
    ensure_song_from_parsed,
    link_file_to_song,
    logical_identity,
    find_song_by_logical_identity,
)


def _path_is_under(path: str, prefix: str) -> bool:
    """True if path is under prefix (normalized)."""
    p = Path(path).resolve()
    pre = Path(prefix).resolve()
    try:
        p.relative_to(pre)
        return True
    except ValueError:
        return False


def _path_is_excluded(path: str, exclude_paths: list[str]) -> bool:
    """True if path is under any exclude_path."""
    return any(_path_is_under(path, ex) for ex in exclude_paths)


def _classify_path(
    path: str,
    library_roots: list[str],
    set_roots: list[str],
    exclude_paths: list[str],
) -> tuple[bool, bool, bool]:
    """Return (is_primary_library, is_set_copy, scan_excluded)."""
    if _path_is_excluded(path, exclude_paths):
        return False, False, True
    under_set = any(_path_is_under(path, r) for r in set_roots)
    under_lib = any(_path_is_under(path, r) for r in library_roots)
    if under_set and not under_lib:
        return False, True, False  # set copy
    return True, False, False  # primary library (or under both; we treat as primary)


def _normalize_path(path_str: str) -> str:
    """Resolve to absolute path for consistent comparison and existence checks."""
    try:
        return str(Path(path_str).resolve())
    except (OSError, RuntimeError):
        return path_str.strip()


def _collect_abc_files(
    roots: list[str],
    exclude_paths: list[str],
) -> list[Path]:
    """Recursively collect all .abc files under roots, skipping excluded dirs."""
    out = []
    seen = set()
    for root in roots:
        root_norm = _normalize_path(root)
        r = Path(root_norm)
        if not r.is_dir():
            continue
        for f in r.rglob("*.abc"):
            try:
                path_str = str(f.resolve())
            except OSError:
                continue
            if _path_is_excluded(path_str, exclude_paths):
                continue
            if path_str in seen:
                continue
            seen.add(path_str)
            if f.is_file():
                out.append(f)
    return out


def _file_mtime_str(path: Path) -> str | None:
    try:
        return str(path.stat().st_mtime)
    except OSError:
        return None


def _file_hash(path: Path) -> str | None:
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


# Duplicate resolution: callback (conn, new_file_path, parsed, existing_song_ids) -> ("link", song_id) | ("separate", None) | ("ignore", None)
DuplicateResolutionResult = tuple[str, int | None]


def run_scan(
    conn: sqlite3.Connection,
    *,
    progress_callback: Callable[[int, int], None] | None = None,
    on_duplicate: Callable[
        [sqlite3.Connection, str, ParsedSong, list[int]], DuplicateResolutionResult
    ] | None = None,
) -> tuple[int, int, int]:
    """
    Scan configured library and set roots, parse .abc files, update DB.
    When a primary-library file has the same logical identity as an existing song,
    on_duplicate is called; return ("link", song_id) to link as variant, ("separate", None) to create new song, ("ignore", None) to skip.
    Returns (files_found, files_scanned, errors).
    """
    lib, set_r, excl = get_enabled_roots(conn)
    library_roots = [_normalize_path(p) for p in lib]
    set_roots = [_normalize_path(p) for p in set_r]
    exclude_paths = [_normalize_path(p) for p in excl]
    # Only scan library roots; set export folder is excluded from scanning (used for export only).
    all_roots = library_roots
    if not all_roots:
        _remove_missing_song_files(conn, set())
        return 0, 0, 0

    files = _collect_abc_files(all_roots, exclude_paths)
    total = len(files)
    scanned = 0
    errors = 0
    scanned_paths: set[str] = set()

    for i, path in enumerate(files):
        if progress_callback:
            progress_callback(i + 1, total)
        path_str = str(path.resolve())
        scanned_paths.add(path_str)
        is_primary, is_set_copy, scan_excluded = _classify_path(
            path_str, library_roots, set_roots, exclude_paths
        )
        try:
            parsed = parse_abc_file(path)
        except Exception:
            errors += 1
            continue
        mtime = _file_mtime_str(path)
        file_hash_val = _file_hash(path)

        # Check if this path already exists (update case)
        cur = conn.execute("SELECT 1 FROM SongFile WHERE file_path = ?", (path_str,))
        if cur.fetchone():
            ensure_song_from_parsed(
                conn,
                parsed,
                path_str,
                file_mtime=mtime,
                file_hash=file_hash_val,
                is_primary_library=is_primary,
                is_set_copy=is_set_copy,
                scan_excluded=scan_excluded,
            )
            scanned += 1
            continue

        # New file: check for primary-library duplicate
        if is_primary and on_duplicate:
            norm_title, composers, part_count = logical_identity(parsed)
            existing_ids = find_song_by_logical_identity(conn, norm_title, composers, part_count)
            if existing_ids:
                action, link_song_id = on_duplicate(conn, path_str, parsed, existing_ids)
                if action == "link" and link_song_id is not None:
                    link_file_to_song(
                        conn,
                        link_song_id,
                        path_str,
                        file_mtime=mtime,
                        file_hash=file_hash_val,
                        export_timestamp=parsed.export_timestamp,
                        is_primary_library=True,
                        is_set_copy=False,
                        scan_excluded=False,
                    )
                    scanned += 1
                elif action == "separate":
                    ensure_song_from_parsed(
                        conn,
                        parsed,
                        path_str,
                        file_mtime=mtime,
                        file_hash=file_hash_val,
                        is_primary_library=is_primary,
                        is_set_copy=is_set_copy,
                        scan_excluded=scan_excluded,
                    )
                    scanned += 1
                # "ignore": do not add, scanned unchanged
                continue

        ensure_song_from_parsed(
            conn,
            parsed,
            path_str,
            file_mtime=mtime,
            file_hash=file_hash_val,
            is_primary_library=is_primary,
            is_set_copy=is_set_copy,
            scan_excluded=scan_excluded,
        )
        scanned += 1

    _remove_missing_song_files(conn, scanned_paths)

    return total, scanned, errors


def _remove_missing_song_files(conn: sqlite3.Connection, current_paths: set[str]) -> None:
    """
    Delete SongFile rows whose file_path is not in current_paths (e.g. after a root was removed).
    Then delete any Song that has no SongFiles left, and their dependent rows (PlayLog, SetlistItem, SongLayout, etc.).
    """
    if not current_paths:
        conn.execute("DELETE FROM SongFile")
    else:
        conn.execute("CREATE TEMP TABLE IF NOT EXISTS _scan_paths (path TEXT PRIMARY KEY)")
        conn.execute("DELETE FROM _scan_paths")
        conn.executemany("INSERT OR IGNORE INTO _scan_paths (path) VALUES (?)", [(p,) for p in current_paths])
        conn.execute("DELETE FROM SongFile WHERE file_path NOT IN (SELECT path FROM _scan_paths)")
        conn.execute("DROP TABLE IF EXISTS _scan_paths")

    conn.execute(
        """DELETE FROM SetlistBandAssignment WHERE setlist_item_id IN
           (SELECT id FROM SetlistItem WHERE song_id NOT IN (SELECT song_id FROM SongFile WHERE song_id IS NOT NULL))"""
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
