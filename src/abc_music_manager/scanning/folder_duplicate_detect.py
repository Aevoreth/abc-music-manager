"""
Detect duplicate folder structures: same relative .abc layout and logical identity per path.

Only primary-library files under each library root are considered (same as scan collection).
Clusters are grouped per library root; nested paths in the same group are filtered to an antichain
(no directory is a strict subdirectory of another in the cluster).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from ..parsing.abc_parser import parse_abc_file
from ..db.song_repo import logical_identity


LogicalIdentityTuple = tuple[str, str, int]


@dataclass(frozen=True)
class FolderDuplicateCluster:
    """Two or more directory roots under the same library mount with identical subtree signatures."""

    library_root: str
    root_paths: tuple[str, ...]
    file_count: int
    sample_titles: tuple[str, ...]


def _best_library_root_for_path(path_str: str, library_roots: list[str]) -> str | None:
    """Longest matching library root containing path_str."""
    p = Path(path_str).resolve()
    best: str | None = None
    best_len = -1
    for r in library_roots:
        try:
            rp = Path(r).resolve()
            p.relative_to(rp)
            if len(str(rp)) > best_len:
                best_len = len(str(rp))
                best = str(rp)
        except ValueError:
            continue
    return best


def _is_strict_parent_dir(ancestor_norm: str, descendant_norm: str) -> bool:
    if ancestor_norm == descendant_norm:
        return False
    a = Path(ancestor_norm)
    b = Path(descendant_norm)
    try:
        b.relative_to(a)
        return True
    except ValueError:
        return False


def _filter_antichain(paths: list[str]) -> list[str]:
    """
    Drop any path that lies strictly under another path in the set (keep shallower duplicates).
    """
    uniq = list(dict.fromkeys(paths))  # preserve order, unique
    return [p for p in uniq if not any(_is_strict_parent_dir(o, p) for o in uniq if o != p)]


def detect_duplicate_folder_clusters(
    library_roots: list[str],
    set_roots: list[str],
    exclude_paths: list[str],
    *,
    progress_callback: Callable[[int, int], None] | None = None,
) -> list[FolderDuplicateCluster]:
    """
    Walk library roots, parse each .abc, build per-directory signatures, return duplicate clusters.
    Only includes primary-library files (not set-only copies, not scan-excluded).
    """
    from .scanner import _classify_path, _collect_abc_files, _normalize_path

    lib_norm = [_normalize_path(p) for p in library_roots]
    set_norm = [_normalize_path(p) for p in set_roots]
    excl_norm = [_normalize_path(p) for p in exclude_paths]

    files = _collect_abc_files(lib_norm, excl_norm)
    total_files = len(files)

    # dir_key -> (rel, identity, title sample)
    contributions: dict[str, list[tuple[str, LogicalIdentityTuple, str]]] = defaultdict(list)
    for i, path in enumerate(files):
        if progress_callback:
            progress_callback(i + 1, total_files)
        path_str = str(path.resolve())
        is_primary, _is_set_copy, scan_excluded = _classify_path(
            path_str, lib_norm, set_norm, excl_norm
        )
        if not is_primary or scan_excluded:
            continue

        root = _best_library_root_for_path(path_str, lib_norm)
        if not root:
            continue

        try:
            parsed = parse_abc_file(path)
        except Exception:
            continue

        ident = logical_identity(parsed)
        title_sample = (parsed.title or Path(path_str).stem).strip()

        pfile = Path(path_str).resolve()
        rroot = Path(root).resolve()
        cur = pfile.parent
        while True:
            rel = pfile.relative_to(cur).as_posix().lower()
            contributions[str(cur.resolve())].append((rel, ident, title_sample))
            if cur.resolve() == rroot:
                break
            parent = cur.parent
            if parent == cur:
                break
            cur = parent

    # Build signature: sorted (rel, ident) only - drop title from signature key
    def _signature(entries: list[tuple[str, LogicalIdentityTuple, str]]) -> tuple[tuple[str, LogicalIdentityTuple], ...]:
        stripped = [(e[0], e[1]) for e in entries]
        return tuple(sorted(stripped))

    dir_to_sig: dict[str, tuple[tuple[str, LogicalIdentityTuple], ...]] = {}
    titles_for_dir: dict[str, list[str]] = defaultdict(list)
    for d, raw in contributions.items():
        sig = _signature(raw)
        dir_to_sig[d] = sig
        for _r, _i, t in raw:
            if t and t not in titles_for_dir[d]:
                titles_for_dir[d].append(t)
            if len(titles_for_dir[d]) >= 5:
                break

    # Files in subtree per directory (one contribution row per file under that dir)
    file_counts: dict[str, int] = {d: len(contributions[d]) for d in dir_to_sig}

    # bucket: (library_root, signature) -> dirs
    buckets: dict[tuple[str, tuple], list[str]] = defaultdict(list)
    for d, sig in dir_to_sig.items():
        lr = _best_library_root_for_path(d, lib_norm)
        if not lr:
            continue
        buckets[(lr, sig)].append(d)

    clusters: list[FolderDuplicateCluster] = []
    for (lr, sig), dirs in buckets.items():
        if len(dirs) < 2:
            continue
        filtered = _filter_antichain(dirs)
        if len(filtered) < 2:
            continue
        filtered.sort(key=str.lower)
        fc = max(file_counts.get(d, 0) for d in filtered)
        samples: list[str] = []
        for d in filtered:
            for t in titles_for_dir.get(d, []):
                if t not in samples:
                    samples.append(t)
                if len(samples) >= 5:
                    break
            if len(samples) >= 5:
                break
        clusters.append(
            FolderDuplicateCluster(
                library_root=lr,
                root_paths=tuple(filtered),
                file_count=fc,
                sample_titles=tuple(samples[:5]),
            )
        )

    clusters.sort(key=lambda c: (-len(c.root_paths), c.library_root.lower(), c.root_paths[0].lower()))
    return clusters
