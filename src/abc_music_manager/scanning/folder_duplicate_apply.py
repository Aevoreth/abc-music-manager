"""Apply user resolutions for duplicate folder clusters (unindex or move to Recycle Bin)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

try:
    from send2trash import send2trash
except ImportError:
    send2trash = None  # type: ignore[misc, assignment]

from ..db.songfile_cleanup import delete_songfiles_for_paths


LoseDisposition = Literal["unindex", "trash"]


@dataclass
class FolderClusterApply:
    """One cluster: keep this root; each loser path with disposition."""

    keep_root: str
    losers: list[tuple[str, LoseDisposition]]


def collect_abc_paths_under_directory(root: str) -> list[str]:
    """All .abc files under root (recursive), resolved absolute paths."""
    r = Path(root)
    if not r.is_dir():
        return []
    out: list[str] = []
    for p in r.rglob("*.abc"):
        if p.is_file():
            try:
                out.append(str(p.resolve()))
            except OSError:
                continue
    return out


def apply_folder_cluster_resolutions(
    conn,
    resolutions: list[FolderClusterApply],
) -> tuple[set[str], list[str]]:
    """
    Apply unindex/trash for each loser folder.

    For trash: move paths to Recycle Bin first, then remove SongFile rows.
    For unindex: only remove SongFile rows.

    Returns (normalized_lose_roots, error_messages).
    """
    lose_roots: set[str] = set()
    errors: list[str] = []

    for res in resolutions:
        for lose_path, disposition in res.losers:
            norm = _normalize_dir(lose_path)
            lose_roots.add(norm)
            paths = collect_abc_paths_under_directory(norm)
            if not paths and not Path(norm).is_dir():
                errors.append(f"Not a directory or empty: {lose_path}")
                continue

            if disposition == "trash":
                if not send2trash:
                    errors.append(
                        "send2trash is not installed; cannot move to Recycle Bin. "
                        "Remove those folders from the library only, or install send2trash."
                    )
                    delete_songfiles_for_paths(conn, paths)
                    continue
                for fpath in sorted(paths, key=len, reverse=True):
                    if Path(fpath).is_file():
                        try:
                            send2trash(fpath)
                        except Exception as e:
                            errors.append(f"Could not move to Recycle Bin: {fpath} ({e})")
                if Path(norm).is_dir():
                    try:
                        send2trash(norm)
                    except Exception as e:
                        errors.append(f"Could not move folder to Recycle Bin: {norm} ({e})")
                delete_songfiles_for_paths(conn, paths)
            else:
                delete_songfiles_for_paths(conn, paths)

    return lose_roots, errors


def _normalize_dir(p: str) -> str:
    try:
        return str(Path(p).resolve())
    except OSError:
        return p


def path_is_under_any_root(path: str, roots: set[str]) -> bool:
    """True if path (file or dir) is exactly one of roots or under one of roots."""
    try:
        p = Path(path).resolve()
    except OSError:
        return False
    for r in roots:
        try:
            rp = Path(r).resolve()
            if p == rp:
                return True
            p.relative_to(rp)
            return True
        except ValueError:
            continue
    return False
