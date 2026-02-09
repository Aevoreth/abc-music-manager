"""
SQLite schema for ABC Music Manager.
Matches DATA_MODEL.md exactly. All tables and fields as specified.
"""

import os
import sqlite3
from pathlib import Path


def get_db_path() -> Path:
    """Return path to the application SQLite database (local, in user data dir)."""
    base = Path(os.environ.get("ABC_MUSIC_MANAGER_DATA", "")) or Path.home() / ".abc_music_manager"
    base.mkdir(parents=True, exist_ok=True)
    return base / "abc_music_manager.sqlite"


def create_schema(conn: sqlite3.Connection) -> None:
    """
    Create all tables per DATA_MODEL.md. Idempotent: uses IF NOT EXISTS.
    Caller may run seed_defaults() after this to insert default Status/Instrument rows.
    """
    conn.execute("PRAGMA foreign_keys = ON")

    # --- 1. Core entities ---
    conn.execute("""
        CREATE TABLE IF NOT EXISTS Instrument (
            id INTEGER PRIMARY KEY,
            name TEXT UNIQUE NOT NULL,
            alternative_names TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS Status (
            id INTEGER PRIMARY KEY,
            name TEXT UNIQUE NOT NULL,
            color TEXT,
            sort_order INTEGER,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS Song (
            id INTEGER PRIMARY KEY,
            title TEXT NOT NULL,
            composers TEXT NOT NULL,
            duration_seconds INTEGER,
            transcriber TEXT,
            rating INTEGER,
            status_id INTEGER REFERENCES Status(id),
            notes TEXT,
            lyrics TEXT,
            last_played_at TEXT,
            total_plays INTEGER NOT NULL DEFAULT 0,
            parts TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS SongFile (
            id INTEGER PRIMARY KEY,
            song_id INTEGER REFERENCES Song(id),
            file_path TEXT UNIQUE NOT NULL,
            file_mtime TEXT,
            file_hash TEXT,
            export_timestamp TEXT,
            is_primary_library INTEGER NOT NULL DEFAULT 1,
            is_set_copy INTEGER NOT NULL DEFAULT 0,
            scan_excluded INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)

    # --- 4. Bands & layouts (before Setlist / PlayLog / SongLayout) ---
    conn.execute("""
        CREATE TABLE IF NOT EXISTS Band (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS Player (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS PlayerInstrument (
            id INTEGER PRIMARY KEY,
            player_id INTEGER NOT NULL REFERENCES Player(id),
            instrument_id INTEGER NOT NULL REFERENCES Instrument(id),
            has_instrument INTEGER NOT NULL DEFAULT 1,
            has_proficiency INTEGER NOT NULL DEFAULT 0,
            notes TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS BandMember (
            band_id INTEGER NOT NULL REFERENCES Band(id),
            player_id INTEGER NOT NULL REFERENCES Player(id),
            PRIMARY KEY (band_id, player_id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS BandLayout (
            id INTEGER PRIMARY KEY,
            band_id INTEGER NOT NULL REFERENCES Band(id),
            name TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS BandLayoutSlot (
            id INTEGER PRIMARY KEY,
            band_layout_id INTEGER NOT NULL REFERENCES BandLayout(id),
            player_id INTEGER NOT NULL REFERENCES Player(id),
            x INTEGER NOT NULL,
            y INTEGER NOT NULL,
            width_units INTEGER NOT NULL DEFAULT 7,
            height_units INTEGER NOT NULL DEFAULT 5,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)

    # --- 2. Song layouts ---
    conn.execute("""
        CREATE TABLE IF NOT EXISTS SongLayout (
            id INTEGER PRIMARY KEY,
            song_id INTEGER NOT NULL REFERENCES Song(id),
            band_layout_id INTEGER NOT NULL REFERENCES BandLayout(id),
            name TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS SongLayoutAssignment (
            id INTEGER PRIMARY KEY,
            song_layout_id INTEGER NOT NULL REFERENCES SongLayout(id),
            player_id INTEGER NOT NULL REFERENCES Player(id),
            part_number INTEGER,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)

    # --- 3. Setlists ---
    conn.execute("""
        CREATE TABLE IF NOT EXISTS Setlist (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            band_layout_id INTEGER REFERENCES BandLayout(id),
            locked INTEGER NOT NULL DEFAULT 0,
            default_change_duration_seconds INTEGER,
            export_naming_rules TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS SetlistItem (
            id INTEGER PRIMARY KEY,
            setlist_id INTEGER NOT NULL REFERENCES Setlist(id),
            song_id INTEGER NOT NULL REFERENCES Song(id),
            position INTEGER NOT NULL,
            override_change_duration_seconds INTEGER,
            song_layout_id INTEGER REFERENCES SongLayout(id),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)

    # --- PlayLog (references Setlist) ---
    conn.execute("""
        CREATE TABLE IF NOT EXISTS PlayLog (
            id INTEGER PRIMARY KEY,
            song_id INTEGER NOT NULL REFERENCES Song(id),
            played_at TEXT NOT NULL,
            context_setlist_id INTEGER REFERENCES Setlist(id),
            context_note TEXT,
            created_at TEXT NOT NULL
        )
    """)

    # --- 5. Setlist overrides ---
    conn.execute("""
        CREATE TABLE IF NOT EXISTS SetlistBandAssignment (
            id INTEGER PRIMARY KEY,
            setlist_item_id INTEGER NOT NULL REFERENCES SetlistItem(id),
            player_id INTEGER NOT NULL REFERENCES Player(id),
            part_number INTEGER,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)

    # --- 6. Settings & targets ---
    conn.execute("""
        CREATE TABLE IF NOT EXISTS AccountTarget (
            id INTEGER PRIMARY KEY,
            account_name TEXT NOT NULL,
            plugin_data_path TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS FolderRule (
            id INTEGER PRIMARY KEY,
            rule_type TEXT NOT NULL,
            path TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            include_in_export INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)

    # Indexes for common lookups
    conn.execute("CREATE INDEX IF NOT EXISTS idx_songfile_song_id ON SongFile(song_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_song_status_id ON Song(status_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_playlog_song_id ON PlayLog(song_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_playlog_played_at ON PlayLog(played_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_setlistitem_setlist_id ON SetlistItem(setlist_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_folderrule_rule_type ON FolderRule(rule_type)")


# Default statuses shipped with the app (order, name, hex color). Default "Default status" is New.
_DEFAULT_STATUSES = [
    (0, "New", "#0044FF"),
    (1, "Testing", "#FF8800"),
    (2, "Ready", "#00FF00"),
]


def seed_defaults(conn: sqlite3.Connection) -> None:
    """
    Insert default Status rows (New, Testing, Ready) with colors only when the Status table is empty.
    Does not update existing statuses, so user customizations (e.g. colors) are preserved.
    """
    cur = conn.execute("SELECT COUNT(*) FROM Status")
    if cur.fetchone()[0] > 0:
        return
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    for sort_order, name, color in _DEFAULT_STATUSES:
        conn.execute(
            "INSERT INTO Status (id, name, color, sort_order, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            (sort_order + 1, name, color, sort_order, now, now),
        )
    conn.commit()


def _migrate_status_drop_is_active(conn: sqlite3.Connection) -> None:
    """If Status table has is_active column, recreate table without it (all statuses are active)."""
    cur = conn.execute("PRAGMA table_info(Status)")
    columns = [row[1] for row in cur.fetchall()]
    if "is_active" not in columns:
        return
    conn.execute("""
        CREATE TABLE Status_new (
            id INTEGER PRIMARY KEY,
            name TEXT UNIQUE NOT NULL,
            color TEXT,
            sort_order INTEGER,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    conn.execute(
        "INSERT INTO Status_new (id, name, color, sort_order, created_at, updated_at)"
        " SELECT id, name, color, sort_order, created_at, updated_at FROM Status"
    )
    conn.execute("DROP TABLE Status")
    conn.execute("ALTER TABLE Status_new RENAME TO Status")
    conn.commit()


def _backfill_song_status_ids(conn: sqlite3.Connection) -> None:
    """Set status_id to the effective default for any song that has none."""
    from .status_repo import get_effective_default_status_id
    default_id = get_effective_default_status_id(conn)
    if default_id:
        conn.execute("UPDATE Song SET status_id = ? WHERE status_id IS NULL", (default_id,))
        conn.commit()


def _migrate_folder_rule_include_in_export(conn: sqlite3.Connection) -> None:
    """Add include_in_export column to FolderRule if missing (for excluded-dirs export flag)."""
    cur = conn.execute("PRAGMA table_info(FolderRule)")
    columns = [row[1] for row in cur.fetchall()]
    if "include_in_export" in columns:
        return
    conn.execute("ALTER TABLE FolderRule ADD COLUMN include_in_export INTEGER NOT NULL DEFAULT 0")
    conn.commit()


def init_database(db_path: Path | None = None) -> sqlite3.Connection:
    """
    Create or open the database at db_path (default: get_db_path()), create schema, run migrations, seed defaults.
    Returns an open connection (caller is responsible for closing or using as context manager).
    """
    path = db_path or get_db_path()
    conn = sqlite3.connect(str(path))
    create_schema(conn)
    _migrate_status_drop_is_active(conn)
    _migrate_folder_rule_include_in_export(conn)
    seed_defaults(conn)
    _backfill_song_status_ids(conn)
    return conn
