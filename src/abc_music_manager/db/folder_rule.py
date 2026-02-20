"""
FolderRule CRUD. Excluded directories only (library/set roots from preferences).
rule_type is kept for compatibility; only "exclude" is used. include_in_export: include in SongbookData export.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from ..services.preferences import get_lotro_root, get_set_export_dir


RuleType = Literal["library_root", "set_root", "exclude"]


@dataclass
class FolderRuleRow:
    id: int
    rule_type: RuleType
    path: str
    enabled: bool
    include_in_export: bool
    created_at: str
    updated_at: str


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def list_folder_rules(conn: sqlite3.Connection) -> list[FolderRuleRow]:
    """Return all folder rules, ordered by rule_type then id."""
    cur = conn.execute(
        "SELECT id, rule_type, path, enabled, include_in_export, created_at, updated_at FROM FolderRule ORDER BY rule_type, id"
    )
    return [
        FolderRuleRow(
            id=r[0],
            rule_type=r[1],
            path=r[2],
            enabled=bool(r[3]),
            include_in_export=bool(r[4]),
            created_at=r[5],
            updated_at=r[6],
        )
        for r in cur.fetchall()
    ]


def add_folder_rule(
    conn: sqlite3.Connection,
    rule_type: RuleType,
    path: str,
    enabled: bool = True,
    include_in_export: bool = False,
) -> int:
    """Insert a FolderRule (typically rule_type='exclude'). Returns new id."""
    now = _now()
    cur = conn.execute(
        """INSERT INTO FolderRule (rule_type, path, enabled, include_in_export, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (rule_type, path.strip(), 1 if enabled else 0, 1 if include_in_export else 0, now, now),
    )
    conn.commit()
    return cur.lastrowid


def update_folder_rule(
    conn: sqlite3.Connection,
    rule_id: int,
    *,
    path: str | None = None,
    enabled: bool | None = None,
    include_in_export: bool | None = None,
) -> None:
    """Update path, enabled, and/or include_in_export for a FolderRule."""
    updates = []
    args = []
    if path is not None:
        updates.append("path = ?")
        args.append(path.strip())
    if enabled is not None:
        updates.append("enabled = ?")
        args.append(1 if enabled else 0)
    if include_in_export is not None:
        updates.append("include_in_export = ?")
        args.append(1 if include_in_export else 0)
    if not updates:
        return
    updates.append("updated_at = ?")
    args.append(_now())
    args.append(rule_id)
    conn.execute(
        f"UPDATE FolderRule SET {', '.join(updates)} WHERE id = ?",
        args,
    )
    conn.commit()


def delete_folder_rule(conn: sqlite3.Connection, rule_id: int) -> None:
    """Delete a FolderRule by id."""
    conn.execute("DELETE FROM FolderRule WHERE id = ?", (rule_id,))
    conn.commit()


def get_enabled_roots(
    conn: sqlite3.Connection,
) -> tuple[list[str], list[str], list[str]]:
    """
    Return (library_roots, set_roots, exclude_paths) for library scanning.
    Library root = single LOTRO root/Music. Scan Music in full; exclude_paths are exceptions.
    Set Export dir and FolderRule excludes are both in exclude_paths (not scanned for library).
    set_roots is still returned for SongbookData export (separate use).
    """
    library_roots = []
    set_roots = []
    lotro = get_lotro_root()
    if lotro:
        music = Path(lotro) / "Music"
        try:
            if music.exists() and music.is_dir():
                library_roots.append(str(music.resolve()))
        except (OSError, RuntimeError):
            pass
    set_export = get_set_export_dir()
    if set_export:
        try:
            p = Path(set_export)
            if p.exists() and p.is_dir():
                set_roots.append(str(p.resolve()))
        except (OSError, RuntimeError):
            pass
    cur = conn.execute(
        "SELECT rule_type, path FROM FolderRule WHERE enabled = 1 AND rule_type = 'exclude'"
    )
    music_root = Path(get_lotro_root()) / "Music" if get_lotro_root() else None
    exclude_paths = []
    # Add Set Export dir so library scan skips it (Music root scanned in full, set dir is exception).
    if set_export:
        try:
            exclude_paths.append(str(Path(set_export).resolve()))
        except (OSError, RuntimeError):
            pass
    for _rt, path in cur.fetchall():
        try:
            p = Path(path)
            if p.is_absolute():
                exclude_paths.append(path)
            elif music_root and str(music_root):
                resolved = (music_root / p).resolve()
                exclude_paths.append(str(resolved))
            else:
                exclude_paths.append(path)
        except (OSError, RuntimeError, ValueError):
            exclude_paths.append(path)
    return library_roots, set_roots, exclude_paths


@dataclass
class ExcludeRuleForExport:
    """Resolved path and include_in_export for SongbookData nested-exclude logic."""
    resolved_path: str
    include_in_export: bool


def get_exclude_rules_for_songbook(conn: sqlite3.Connection) -> list[ExcludeRuleForExport]:
    """
    Return enabled exclude rules with resolved paths and include_in_export.
    Used when building SongbookData: include a path under an exclude only if the
    most specific (longest) matching exclude has include_in_export True.
    """
    music_root = Path(get_lotro_root()) / "Music" if get_lotro_root() else None
    cur = conn.execute(
        "SELECT path, include_in_export FROM FolderRule WHERE enabled = 1 AND rule_type = 'exclude'"
    )
    rules = []
    for path, include_in_export in cur.fetchall():
        try:
            p = Path(path)
            if p.is_absolute():
                resolved = str(p.resolve())
            elif music_root and str(music_root):
                resolved = str((music_root / p).resolve())
            else:
                resolved = path
            rules.append(ExcludeRuleForExport(resolved_path=resolved, include_in_export=bool(include_in_export)))
        except (OSError, RuntimeError, ValueError):
            rules.append(ExcludeRuleForExport(resolved_path=path, include_in_export=bool(include_in_export)))
    return rules
