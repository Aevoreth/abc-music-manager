"""AccountTarget CRUD for PluginData writing. DATA_MODEL §6."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class AccountTargetRow:
    id: int
    account_name: str
    plugin_data_path: str
    enabled: bool
    created_at: str
    updated_at: str


def list_account_targets(conn: sqlite3.Connection) -> list[AccountTargetRow]:
    cur = conn.execute(
        "SELECT id, account_name, plugin_data_path, enabled, created_at, updated_at FROM AccountTarget ORDER BY account_name"
    )
    return [
        AccountTargetRow(
            id=r[0],
            account_name=r[1],
            plugin_data_path=r[2],
            enabled=bool(r[3]),
            created_at=r[4],
            updated_at=r[5],
        )
        for r in cur.fetchall()
    ]


def add_account_target(
    conn: sqlite3.Connection,
    account_name: str,
    plugin_data_path: str,
    enabled: bool = True,
) -> int:
    now = _now()
    cur = conn.execute(
        """INSERT INTO AccountTarget (account_name, plugin_data_path, enabled, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?)""",
        (account_name.strip(), plugin_data_path.strip(), 1 if enabled else 0, now, now),
    )
    conn.commit()
    return cur.lastrowid


def update_account_target(
    conn: sqlite3.Connection,
    target_id: int,
    *,
    account_name: str | None = None,
    plugin_data_path: str | None = None,
    enabled: bool | None = None,
) -> None:
    updates = []
    args = []
    if account_name is not None:
        updates.append("account_name = ?")
        args.append(account_name.strip())
    if plugin_data_path is not None:
        updates.append("plugin_data_path = ?")
        args.append(plugin_data_path.strip())
    if enabled is not None:
        updates.append("enabled = ?")
        args.append(1 if enabled else 0)
    if not updates:
        return
    updates.append("updated_at = ?")
    args.append(_now())
    args.append(target_id)
    conn.execute(f"UPDATE AccountTarget SET {', '.join(updates)} WHERE id = ?", args)
    conn.commit()


def delete_account_target(conn: sqlite3.Connection, target_id: int) -> None:
    conn.execute("DELETE FROM AccountTarget WHERE id = ?", (target_id,))
    conn.commit()
