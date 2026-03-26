"""
Filesystem scanner: discover .abc files under library roots, parse and index.
Duplicate collisions in the primary library are deferred and resolved via on_duplicates_batch (UI).
"""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path
from typing import Callable

try:
    from send2trash import send2trash
except ImportError:
    send2trash = None


def _send_to_trash(path: str) -> None:
    """Move file to recycle bin/trash. No-op if send2trash unavailable."""
    if send2trash and Path(path).is_file():
        try:
            send2trash(path)
        except Exception:
            pass


from ..parsing.abc_parser import parse_abc_file, ParsedSong
from ..db.folder_rule import get_enabled_roots
from ..db.song_repo import (
    ensure_song_from_parsed,
    get_file_paths_for_song,
    logical_identity,
    find_song_by_logical_identity,
    relocate_song_file,
)
from ..db.songfile_cleanup import cleanup_orphaned_songs_after_songfile_deletion
from .duplicate_types import DuplicateCandidate, DuplicateDecision
from .folder_duplicate_detect import FolderDuplicateCluster


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


def _apply_duplicate_resolution(
    conn: sqlite3.Connection,
    candidate: DuplicateCandidate,
    action: str,
    existing_song_id: int | None,
) -> int:
    """
    Apply one duplicate decision. Returns increment to scanned count (0 or 1).
    """
    path_str = candidate.new_path
    parsed = candidate.parsed
    mtime = candidate.mtime
    file_hash_val = candidate.file_hash
    is_primary = candidate.is_primary
    is_set_copy = candidate.is_set_copy
    scan_excluded = candidate.scan_excluded

    if action == "keep_existing":
        return 0
    if action == "keep_existing_delete_new":
        _send_to_trash(path_str)
        return 0
    if action == "keep_new" and existing_song_id is not None:
        existing_paths = get_file_paths_for_song(conn, existing_song_id)
        if existing_paths:
            relocate_song_file(
                conn,
                existing_song_id,
                existing_paths[0],
                path_str,
                parsed,
                file_mtime=mtime,
                file_hash=file_hash_val,
                is_primary_library=is_primary,
                is_set_copy=is_set_copy,
                scan_excluded=scan_excluded,
            )
            return 1
        return 0
    if action == "keep_new_delete_existing" and existing_song_id is not None:
        existing_paths = get_file_paths_for_song(conn, existing_song_id)
        if existing_paths:
            old_path = existing_paths[0]
            relocate_song_file(
                conn,
                existing_song_id,
                old_path,
                path_str,
                parsed,
                file_mtime=mtime,
                file_hash=file_hash_val,
                is_primary_library=is_primary,
                is_set_copy=is_set_copy,
                scan_excluded=scan_excluded,
            )
            _send_to_trash(old_path)
            return 1
        return 0
    if action == "separate":
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
        return 1
    # ignore and unknown: do not index new file
    return 0


def run_scan(
    conn: sqlite3.Connection,
    *,
    progress_callback: Callable[[int, int], None] | None = None,
    on_duplicates_batch: Callable[
        [sqlite3.Connection, list[DuplicateCandidate]],
        list[DuplicateDecision] | None,
    ]
    | None = None,
    on_folder_duplicates_review: Callable[
        [sqlite3.Connection, list[FolderDuplicateCluster], list[DuplicateCandidate]],
        set[str],
    ]
    | None = None,
) -> tuple[int, int, int]:
    """
    Scan configured library roots, parse .abc files, update DB.
    When a primary-library file has the same logical identity as an existing song,
    indexing is deferred until phase 2. If on_duplicates_batch is provided, all true
    duplicates (after move detection) are passed to it once; the returned decisions
    are applied in order. If the callback returns None (e.g. user cancelled), each
    pending duplicate is treated as ignore (new file not indexed).
    If on_duplicates_batch is None, deferred duplicates are not used—new files are
    indexed immediately (separate Song rows) like the legacy no-callback behavior.

    If on_folder_duplicates_review is set and there are pending file duplicates, duplicate
    folder clusters may be detected first; the callback returns normalized paths of folders
    that were unindexed or trashed so pending file duplicates under those paths are dropped.

    Returns (files_found, files_scanned, errors).
    """
    lib, set_r, excl = get_enabled_roots(conn)
    library_roots = [_normalize_path(p) for p in lib]
    set_roots = [_normalize_path(p) for p in set_r]
    exclude_paths = [_normalize_path(p) for p in excl]
    all_roots = library_roots
    if not all_roots:
        _remove_missing_song_files(conn, set())
        return 0, 0, 0

    files = _collect_abc_files(all_roots, exclude_paths)
    total = len(files)
    scanned = 0
    errors = 0
    scanned_paths: set[str] = set()
    deferred_duplicates: list[
        tuple[str, ParsedSong, str | None, str | None, bool, bool, bool, list[int]]
    ] = []

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

        if is_primary and on_duplicates_batch:
            norm_title, composers, part_count = logical_identity(parsed)
            existing_ids = find_song_by_logical_identity(conn, norm_title, composers, part_count)
            if existing_ids:
                deferred_duplicates.append(
                    (path_str, parsed, mtime, file_hash_val, is_primary, is_set_copy, scan_excluded, existing_ids)
                )
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

    pending_true: list[DuplicateCandidate] = []

    for path_str, parsed, mtime, file_hash_val, is_primary, is_set_copy, scan_excluded, existing_ids in deferred_duplicates:
        move_song_id: int | None = None
        move_old_path: str | None = None
        for sid in existing_ids:
            existing_paths = get_file_paths_for_song(conn, sid)
            missing_paths = [p for p in existing_paths if p not in scanned_paths]
            if len(missing_paths) == 1 and len(existing_paths) == 1:
                move_song_id = sid
                move_old_path = missing_paths[0]
                break

        if move_song_id is not None and move_old_path is not None:
            relocate_song_file(
                conn,
                move_song_id,
                move_old_path,
                path_str,
                parsed,
                file_mtime=mtime,
                file_hash=file_hash_val,
                is_primary_library=is_primary,
                is_set_copy=is_set_copy,
                scan_excluded=scan_excluded,
            )
            scanned += 1
            continue

        pending_true.append(
            DuplicateCandidate(
                new_path=path_str,
                parsed=parsed,
                mtime=mtime,
                file_hash=file_hash_val,
                is_primary=is_primary,
                is_set_copy=is_set_copy,
                scan_excluded=scan_excluded,
                existing_song_ids=list(existing_ids),
            )
        )

    if (
        pending_true
        and on_duplicates_batch
        and on_folder_duplicates_review
        and library_roots
    ):
        from .folder_duplicate_apply import path_is_under_any_root
        from .folder_duplicate_detect import detect_duplicate_folder_clusters

        folder_clusters = detect_duplicate_folder_clusters(
            library_roots, set_roots, exclude_paths
        )
        if folder_clusters:
            losing_roots = on_folder_duplicates_review(conn, folder_clusters, pending_true)
            if losing_roots:
                pending_true = [
                    c
                    for c in pending_true
                    if not path_is_under_any_root(c.new_path, losing_roots)
                ]

    if pending_true and on_duplicates_batch:
        decisions = on_duplicates_batch(conn, pending_true)
        if (
            decisions is None
            or len(decisions) != len(pending_true)
            or any(c.new_path != d.new_path for c, d in zip(pending_true, decisions))
        ):
            decisions = [DuplicateDecision(c.new_path, "ignore", None) for c in pending_true]

        for cand, dec in zip(pending_true, decisions):
            scanned += _apply_duplicate_resolution(
                conn, cand, dec.action, dec.existing_song_id
            )

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

    cleanup_orphaned_songs_after_songfile_deletion(conn)
