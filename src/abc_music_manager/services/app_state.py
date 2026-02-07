"""
App-wide state: database connection. Single place for UI and services to obtain conn.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from ..db.schema import get_db_path, init_database


class AppState:
    """Holds the application SQLite connection. Create at startup, close on exit."""

    def __init__(self, db_path: Path | None = None) -> None:
        self._conn: sqlite3.Connection | None = init_database(db_path)

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("Database connection is closed")
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> AppState:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
