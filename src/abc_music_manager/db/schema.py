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
            export_column_order TEXT,
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
        CREATE TABLE IF NOT EXISTS SetlistFolder (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS Setlist (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            band_layout_id INTEGER REFERENCES BandLayout(id),
            folder_id INTEGER REFERENCES SetlistFolder(id),
            sort_order INTEGER NOT NULL DEFAULT 0,
            locked INTEGER NOT NULL DEFAULT 0,
            default_change_duration_seconds INTEGER,
            export_naming_rules TEXT,
            notes TEXT,
            set_date TEXT,
            set_time TEXT,
            target_duration_seconds INTEGER,
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


def _migrate_band_notes(conn: sqlite3.Connection) -> None:
    """Add notes column to Band table if missing."""
    cur = conn.execute("PRAGMA table_info(Band)")
    columns = [row[1] for row in cur.fetchall()]
    if "notes" in columns:
        return
    conn.execute("ALTER TABLE Band ADD COLUMN notes TEXT")
    conn.commit()


def _migrate_setlist_notes(conn: sqlite3.Connection) -> None:
    """Add notes column to Setlist table if missing."""
    cur = conn.execute("PRAGMA table_info(Setlist)")
    columns = [row[1] for row in cur.fetchall()]
    if "notes" in columns:
        return
    conn.execute("ALTER TABLE Setlist ADD COLUMN notes TEXT")
    conn.commit()


def _migrate_setlist_date_time_target(conn: sqlite3.Connection) -> None:
    """Add set_date, set_time, target_duration_seconds to Setlist if missing."""
    cur = conn.execute("PRAGMA table_info(Setlist)")
    columns = [row[1] for row in cur.fetchall()]
    if "set_date" not in columns:
        conn.execute("ALTER TABLE Setlist ADD COLUMN set_date TEXT")
        conn.commit()
    if "set_time" not in columns:
        conn.execute("ALTER TABLE Setlist ADD COLUMN set_time TEXT")
        conn.commit()
    if "target_duration_seconds" not in columns:
        conn.execute("ALTER TABLE Setlist ADD COLUMN target_duration_seconds INTEGER")
        conn.commit()


def _migrate_setlist_folders(conn: sqlite3.Connection) -> None:
    """Add SetlistFolder table and folder_id, sort_order to Setlist if missing."""
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='SetlistFolder'"
    )
    if cur.fetchone() is None:
        conn.execute("""
            CREATE TABLE SetlistFolder (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        conn.commit()
    cur = conn.execute("PRAGMA table_info(Setlist)")
    columns = [row[1] for row in cur.fetchall()]
    if "folder_id" not in columns:
        conn.execute("ALTER TABLE Setlist ADD COLUMN folder_id INTEGER REFERENCES SetlistFolder(id)")
        conn.commit()
    if "sort_order" not in columns:
        conn.execute("ALTER TABLE Setlist ADD COLUMN sort_order INTEGER NOT NULL DEFAULT 0")
        conn.commit()


# 24 LOTRO instruments for Players tab possession grid (user-specified order).
# Exported for use by player_repo and bands_view.
PLAYER_INSTRUMENTS = [
    "Basic Fiddle",
    "Student Fiddle",
    "Bardic Fiddle",
    "Lonely Mountain Fiddle",
    "Sprightly Fiddle",
    "Traveler's Trusty Fiddle",
    "Basic Bassoon",
    "Lonely Mountain Bassoon",
    "Brusque Bassoon",
    "Basic Flute",
    "Basic Horn",
    "Basic Clarinet",
    "Basic Bagpipe",
    "Basic Pibgorn",
    "Basic Harp",
    "Misty Mountain Harp",
    "Basic Lute",
    "Lute of Ages",
    "Basic Theorbo",
    "Basic Drum",
    "Basic Cowbell",
    "Moor Cowbell",
    "Jaunty Hand-Knells",
]


def _migrate_band_layout_export_column_order(conn: sqlite3.Connection) -> None:
    """Add export_column_order column to BandLayout if missing (JSON array of player_ids for CSV column order)."""
    cur = conn.execute("PRAGMA table_info(BandLayout)")
    columns = [row[1] for row in cur.fetchall()]
    if "export_column_order" in columns:
        return
    conn.execute("ALTER TABLE BandLayout ADD COLUMN export_column_order TEXT")
    conn.commit()


def _migrate_player_level_class(conn: sqlite3.Connection) -> None:
    """Add level and class columns to Player table if missing."""
    cur = conn.execute("PRAGMA table_info(Player)")
    columns = [row[1] for row in cur.fetchall()]
    if "level" not in columns:
        conn.execute("ALTER TABLE Player ADD COLUMN level INTEGER")
        conn.commit()
    if "class" not in columns:
        conn.execute("ALTER TABLE Player ADD COLUMN class TEXT")
        conn.commit()


def _migrate_song_last_layout(conn: sqlite3.Connection) -> None:
    """Add last-used layout columns to Song for layout preference when playing from Library."""
    cur = conn.execute("PRAGMA table_info(Song)")
    columns = [row[1] for row in cur.fetchall()]
    if "last_band_layout_id" not in columns:
        conn.execute("ALTER TABLE Song ADD COLUMN last_band_layout_id INTEGER REFERENCES BandLayout(id)")
        conn.commit()
    if "last_song_layout_id" not in columns:
        conn.execute("ALTER TABLE Song ADD COLUMN last_song_layout_id INTEGER REFERENCES SongLayout(id)")
        conn.commit()
    if "last_setlist_item_id" not in columns:
        conn.execute("ALTER TABLE Song ADD COLUMN last_setlist_item_id INTEGER REFERENCES SetlistItem(id)")
        conn.commit()


def seed_player_instruments(conn: sqlite3.Connection) -> None:
    """Ensure all 24 LOTRO player instruments exist in Instrument table."""
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    for name in PLAYER_INSTRUMENTS:
        cur = conn.execute("SELECT id FROM Instrument WHERE name = ?", (name,))
        if cur.fetchone() is None:
            conn.execute(
                "INSERT INTO Instrument (name, alternative_names, created_at, updated_at) VALUES (?, NULL, ?, ?)",
                (name, now, now),
            )
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
    _migrate_band_notes(conn)
    _migrate_setlist_notes(conn)
    _migrate_setlist_date_time_target(conn)
    _migrate_setlist_folders(conn)
    _migrate_band_layout_export_column_order(conn)
    _migrate_player_level_class(conn)
    _migrate_song_last_layout(conn)
    seed_defaults(conn)
    seed_player_instruments(conn)
    _backfill_song_status_ids(conn)
    return conn
