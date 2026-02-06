"""
FolderRule CRUD. DATA_MODEL §6: rule_type in ("library_root", "set_root", "exclude").
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal


RuleType = Literal["library_root", "set_root", "exclude"]


@dataclass
class FolderRuleRow:
    id: int
    rule_type: RuleType
    path: str
    enabled: bool
    created_at: str
    updated_at: str


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def list_folder_rules(conn: sqlite3.Connection) -> list[FolderRuleRow]:
    """Return all folder rules, ordered by rule_type then id."""
    cur = conn.execute(
        "SELECT id, rule_type, path, enabled, created_at, updated_at FROM FolderRule ORDER BY rule_type, id"
    )
    return [
        FolderRuleRow(
            id=r[0],
            rule_type=r[1],
            path=r[2],
            enabled=bool(r[3]),
            created_at=r[4],
            updated_at=r[5],
        )
        for r in cur.fetchall()
    ]


def add_folder_rule(
    conn: sqlite3.Connection,
    rule_type: RuleType,
    path: str,
    enabled: bool = True,
) -> int:
    """Insert a FolderRule. Returns new id."""
    now = _now()
    cur = conn.execute(
        """INSERT INTO FolderRule (rule_type, path, enabled, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?)""",
        (rule_type, path.strip(), 1 if enabled else 0, now, now),
    )
    conn.commit()
    return cur.lastrowid


def update_folder_rule(
    conn: sqlite3.Connection,
    rule_id: int,
    *,
    path: str | None = None,
    enabled: bool | None = None,
) -> None:
    """Update path and/or enabled for a FolderRule."""
    updates = []
    args = []
    if path is not None:
        updates.append("path = ?")
        args.append(path.strip())
    if enabled is not None:
        updates.append("enabled = ?")
        args.append(1 if enabled else 0)
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
    Return (library_roots, set_roots, exclude_paths) for scanning.
    Only enabled rules are included.
    """
    cur = conn.execute(
        "SELECT rule_type, path FROM FolderRule WHERE enabled = 1"
    )
    library_roots = []
    set_roots = []
    exclude_paths = []
    for rule_type, path in cur.fetchall():
        if rule_type == "library_root":
            library_roots.append(path)
        elif rule_type == "set_root":
            set_roots.append(path)
        elif rule_type == "exclude":
            exclude_paths.append(path)
    return library_roots, set_roots, exclude_paths
