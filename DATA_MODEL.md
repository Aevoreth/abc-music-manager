# Data Model (Draft) — ABC Music Manager

This data model is designed for SQLite and reflects key project decisions:
- `.abc` files on disk are the source of truth for song content and tag-derived metadata.
- Maestro comment tags are authoritative when present.
- Musical ABC note bodies are not stored in the database.
- Composer is normalized and linked via a many-to-many relationship.
- Duplicate handling is supported by tracking multiple files per logical song.

---

## 1. Core Entities

## Song
Represents the logical song shown in the library UI (not a specific file copy).

Fields:
- id (INTEGER PK)
- title (TEXT)
- duration_seconds (INTEGER NULL)  
- duration_text (TEXT NULL) — e.g. "3:43" (store original display form when available)
- transcriber (TEXT NULL)
- rating (INTEGER NULL) — 0–5
- status_id (INTEGER FK → Status.id, NULL)
- notes (TEXT NULL) — app-only notes (NOT ABC musical notes)
- lyrics (TEXT NULL)
- last_played_at (DATETIME NULL)
- total_plays (INTEGER NOT NULL DEFAULT 0)
- created_at (DATETIME)
- updated_at (DATETIME)

Notes:
- title/transcriber/duration are generally derived from file tags and kept in sync with the file.
- App-only fields (rating/status/notes/lyrics/play stats) live here.

---

## Composer
Normalized composer names.

Fields:
- id (INTEGER PK)
- name (TEXT UNIQUE) — normalized
- created_at (DATETIME)
- updated_at (DATETIME)

---

## SongComposer (Join Table)
Many-to-many mapping between Song and Composer.

Fields:
- song_id (INTEGER FK → Song.id)
- composer_id (INTEGER FK → Composer.id)
Primary Key:
- (song_id, composer_id)

---

## SongFile
Tracks each on-disk `.abc` file, including duplicates and set/export copies.

Fields:
- id (INTEGER PK)
- song_id (INTEGER FK → Song.id, NULL) — NULL until matched/created
- file_path (TEXT UNIQUE)
- file_mtime (INTEGER or DATETIME)
- file_hash (TEXT NULL) — optional but recommended for robust change detection
- export_timestamp (TEXT NULL) — parsed from `%%export-timestamp` when present
- is_primary_library (BOOLEAN NOT NULL DEFAULT 1)
- is_set_copy (BOOLEAN NOT NULL DEFAULT 0)
- scan_excluded (BOOLEAN NOT NULL DEFAULT 0)
- created_at (DATETIME)
- updated_at (DATETIME)

Notes:
- "Primary library" vs "set copy" is determined by folder rules in Settings.
- Multiple SongFile rows can link to the same Song.

---

## SongPart
Stores per-part metadata derived from each `X:` block.

Fields:
- id (INTEGER PK)
- song_id (INTEGER FK → Song.id)
- part_number (INTEGER) — from `X:`
- part_name (TEXT NULL) — from `%%part-name`
- made_for (TEXT NULL) — from `%%made-for`
- created_at (DATETIME)
- updated_at (DATETIME)

Notes:
- Part count = COUNT(parts) for a song.
- This stores metadata only, not musical note content.

---

## Status
Configurable song status labels.

Fields:
- id (INTEGER PK)
- name (TEXT UNIQUE) — e.g. New, Testing, Ready
- color (TEXT NULL) — UI badge color token (implementation-defined)
- is_active (BOOLEAN NOT NULL DEFAULT 1)
- sort_order (INTEGER NULL)
- created_at (DATETIME)
- updated_at (DATETIME)

---

## PlayLog
Optional but recommended to support “frequency within timeframe” queries.

Fields:
- id (INTEGER PK)
- song_id (INTEGER FK → Song.id)
- played_at (DATETIME)
- context_setlist_id (INTEGER FK → Setlist.id, NULL)
- context_note (TEXT NULL)
- created_at (DATETIME)

Derived:
- Song.last_played_at = MAX(PlayLog.played_at)
- Song.total_plays = COUNT(PlayLog)

---

## 2. Setlists

## Setlist
Fields:
- id (INTEGER PK)
- name (TEXT)
- locked (BOOLEAN NOT NULL DEFAULT 0)
- default_change_duration_seconds (INTEGER NULL)
- export_naming_rules (TEXT NULL) — JSON/text blob
- created_at (DATETIME)
- updated_at (DATETIME)

---

## SetlistItem
Represents a song in a setlist.

Fields:
- id (INTEGER PK)
- setlist_id (INTEGER FK → Setlist.id)
- song_id (INTEGER FK → Song.id)
- position (INTEGER)
- override_change_duration_seconds (INTEGER NULL)
- band_layout_id (INTEGER FK → BandLayout.id, NULL)
- created_at (DATETIME)
- updated_at (DATETIME)

---

## 3. Bands & Layouts

## Band
Fields:
- id (INTEGER PK)
- name (TEXT)
- created_at (DATETIME)
- updated_at (DATETIME)

---

## Player
Fields:
- id (INTEGER PK)
- name (TEXT)
- created_at (DATETIME)
- updated_at (DATETIME)

---

## PlayerInstrument
Fields:
- id (INTEGER PK)
- player_id (INTEGER FK → Player.id)
- instrument_name (TEXT)
- has_instrument (BOOLEAN NOT NULL DEFAULT 1)
- proficiency (INTEGER NULL) — scale/enum TBD
- notes (TEXT NULL)
- created_at (DATETIME)
- updated_at (DATETIME)

---

## BandMember (Join Table)
Maps players to bands.

Fields:
- band_id (INTEGER FK → Band.id)
- player_id (INTEGER FK → Player.id)
Primary Key:
- (band_id, player_id)

---

## BandLayout
Fields:
- id (INTEGER PK)
- band_id (INTEGER FK → Band.id)
- name (TEXT)
- created_at (DATETIME)
- updated_at (DATETIME)

---

## BandLayoutSlot
Represents a player card placed on the grid.

Fields:
- id (INTEGER PK)
- band_layout_id (INTEGER FK → BandLayout.id)
- player_id (INTEGER FK → Player.id)
- x (INTEGER)
- y (INTEGER)
- width_units (INTEGER NOT NULL DEFAULT 7)
- height_units (INTEGER NOT NULL DEFAULT 5)
- created_at (DATETIME)
- updated_at (DATETIME)

---

## 4. Assignments (Library Defaults and Set Overrides)

## SongBandAssignment (Library-level defaults)
Fields:
- id (INTEGER PK)
- song_id (INTEGER FK → Song.id)
- band_layout_id (INTEGER FK → BandLayout.id)
- player_id (INTEGER FK → Player.id)
- part_number (INTEGER)
- instrument_name (TEXT)
- created_at (DATETIME)
- updated_at (DATETIME)

---

## SetlistBandAssignment (Per-set/per-song overrides)
Fields:
- id (INTEGER PK)
- setlist_item_id (INTEGER FK → SetlistItem.id)
- band_layout_id (INTEGER FK → BandLayout.id)
- player_id (INTEGER FK → Player.id)
- part_number (INTEGER)
- instrument_name (TEXT)
- created_at (DATETIME)
- updated_at (DATETIME)

---

## 5. Settings & Targets

## AccountTarget
Used for PluginData writing targets.

Fields:
- id (INTEGER PK)
- account_name (TEXT)
- plugin_data_path (TEXT)
- enabled (BOOLEAN NOT NULL DEFAULT 1)
- created_at (DATETIME)
- updated_at (DATETIME)

---

## FolderRule (recommended)
Defines library roots, set/export folders, and exclusions.

Fields:
- id (INTEGER PK)
- rule_type (TEXT) — "library_root" | "set_root" | "exclude"
- path (TEXT)
- enabled (BOOLEAN NOT NULL DEFAULT 1)
- created_at (DATETIME)
- updated_at (DATETIME)

---

## 6. Uniqueness & Duplicate Strategy (Implementation Notes)

### Logical identity (primary heuristic)
- normalized title + normalized composer set + part count

### Practical behavior
- Many SongFile rows may map to one Song.
- The app should exclude set/export roots from the main library view by default.
- When two primary-library files collide on logical identity:
  - prompt the user to resolve (variants / separate / ignore).
