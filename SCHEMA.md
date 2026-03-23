# Database Schema — ABC Music Manager

SQLite database schema for ABC Music Manager. The database path is `~/.abc_music_manager/abc_music_manager.sqlite` (or `$ABC_MUSIC_MANAGER_DATA/abc_music_manager.sqlite` when set).

This document reflects the **current schema** (v11) after all migrations. See [Migration System](#migration-system) for upgrade behavior.

---

## Tables Overview

| Table | Purpose |
|-------|---------|
| Instrument | Catalog of instruments (e.g. flute, lute, horn) |
| Status | Song status labels (New, Testing, Ready) |
| Song | Logical song entity (one row per song) |
| SongFile | On-disk `.abc` files and their metadata |
| Band | Band/group entity |
| Player | Player/character entity |
| PlayerInstrument | Player→instrument possession and proficiency |
| BandMember | Band↔Player many-to-many join |
| BandLayout | Layout configuration for a band |
| BandLayoutSlot | Player positions on the band grid |
| SongLayout | Song layout for a given band layout |
| SongLayoutAssignment | Player→part mapping per song layout |
| SetlistFolder | Folders for organizing setlists |
| Setlist | A playable set of songs |
| SetlistItem | Song entry within a setlist |
| PlayLog | Play history records |
| SetlistBandAssignment | Per-setlist-item player part overrides |
| AccountTarget | PluginData export targets |
| FolderRule | Excluded folder rules for scanning |
| schema_version | Migration version tracking (internal) |

---

## 1. Core Entities

### Instrument

Catalog of instruments. Used for song parts (`%%made-for` in ABC) and player possession grid.

| Column | Type | Constraints |
|--------|------|-------------|
| id | INTEGER | PRIMARY KEY |
| name | TEXT | UNIQUE NOT NULL |
| alternative_names | TEXT | NULL |
| created_at | TEXT | NOT NULL |
| updated_at | TEXT | NOT NULL |

---

### Status

Configurable song status labels. Ordered by `sort_order`.

| Column | Type | Constraints |
|--------|------|-------------|
| id | INTEGER | PRIMARY KEY |
| name | TEXT | UNIQUE NOT NULL |
| color | TEXT | NULL |
| sort_order | INTEGER | NULL |
| created_at | TEXT | NOT NULL |
| updated_at | TEXT | NOT NULL |

---

### Song

Logical song entity (not a specific file). App-only metadata lives here; ABC content is in files.

| Column | Type | Constraints |
|--------|------|-------------|
| id | INTEGER | PRIMARY KEY |
| title | TEXT | NOT NULL |
| composers | TEXT | NOT NULL |
| duration_seconds | INTEGER | NULL |
| transcriber | TEXT | NULL |
| rating | INTEGER | NULL (0–5) |
| status_id | INTEGER | FK → Status(id), NULL |
| notes | TEXT | NULL |
| lyrics | TEXT | NULL |
| last_played_at | TEXT | NULL |
| total_plays | INTEGER | NOT NULL DEFAULT 0 |
| parts | TEXT | NULL (JSON array) |
| last_band_layout_id | INTEGER | FK → BandLayout(id), NULL |
| last_song_layout_id | INTEGER | FK → SongLayout(id), NULL |
| last_setlist_item_id | INTEGER | FK → SetlistItem(id), NULL |
| created_at | TEXT | NOT NULL |
| updated_at | TEXT | NOT NULL |

`parts` JSON format: `[{"part_number": int, "part_name": str|null, "instrument_id": int|null}, ...]`

---

### SongFile

Tracks each `.abc` file. Multiple files can map to one Song (duplicates, set copies).

| Column | Type | Constraints |
|--------|------|-------------|
| id | INTEGER | PRIMARY KEY |
| song_id | INTEGER | FK → Song(id), NULL |
| file_path | TEXT | UNIQUE NOT NULL |
| file_mtime | TEXT | NULL |
| file_hash | TEXT | NULL |
| export_timestamp | TEXT | NULL |
| is_primary_library | INTEGER | NOT NULL DEFAULT 1 |
| is_set_copy | INTEGER | NOT NULL DEFAULT 0 |
| scan_excluded | INTEGER | NOT NULL DEFAULT 0 |
| created_at | TEXT | NOT NULL |
| updated_at | TEXT | NOT NULL |

---

## 2. Bands & Layouts

### Band

| Column | Type | Constraints |
|--------|------|-------------|
| id | INTEGER | PRIMARY KEY |
| name | TEXT | NOT NULL |
| notes | TEXT | NULL |
| sort_order | INTEGER | NOT NULL DEFAULT 0 |
| created_at | TEXT | NOT NULL |
| updated_at | TEXT | NOT NULL |

---

### Player

| Column | Type | Constraints |
|--------|------|-------------|
| id | INTEGER | PRIMARY KEY |
| name | TEXT | NOT NULL |
| level | INTEGER | NULL |
| class | TEXT | NULL |
| created_at | TEXT | NOT NULL |
| updated_at | TEXT | NOT NULL |

`level` and `class` are optional (e.g. LOTRO character level/class).

---

### PlayerInstrument

Links player to instrument with possession and proficiency.

| Column | Type | Constraints |
|--------|------|-------------|
| id | INTEGER | PRIMARY KEY |
| player_id | INTEGER | FK → Player(id), NOT NULL |
| instrument_id | INTEGER | FK → Instrument(id), NOT NULL |
| has_instrument | INTEGER | NOT NULL DEFAULT 1 |
| has_proficiency | INTEGER | NOT NULL DEFAULT 0 |
| notes | TEXT | NULL |
| created_at | TEXT | NOT NULL |
| updated_at | TEXT | NOT NULL |

---

### BandMember

Band↔Player many-to-many. Composite PK.

| Column | Type | Constraints |
|--------|------|-------------|
| band_id | INTEGER | FK → Band(id), NOT NULL |
| player_id | INTEGER | FK → Player(id), NOT NULL |

PRIMARY KEY (band_id, player_id)

---

### BandLayout

Layout configuration for a band (grid of players).

| Column | Type | Constraints |
|--------|------|-------------|
| id | INTEGER | PRIMARY KEY |
| band_id | INTEGER | FK → Band(id), NOT NULL |
| name | TEXT | NOT NULL |
| export_column_order | TEXT | NULL (JSON array of player_ids) |
| sort_order | INTEGER | NOT NULL DEFAULT 0 |
| created_at | TEXT | NOT NULL |
| updated_at | TEXT | NOT NULL |

---

### BandLayoutSlot

Player position on the band grid.

| Column | Type | Constraints |
|--------|------|-------------|
| id | INTEGER | PRIMARY KEY |
| band_layout_id | INTEGER | FK → BandLayout(id), NOT NULL |
| player_id | INTEGER | FK → Player(id), NOT NULL |
| x | INTEGER | NOT NULL |
| y | INTEGER | NOT NULL |
| width_units | INTEGER | NOT NULL DEFAULT 7 |
| height_units | INTEGER | NOT NULL DEFAULT 5 |
| created_at | TEXT | NOT NULL |
| updated_at | TEXT | NOT NULL |

---

## 3. Song Layouts

### SongLayout

Player→part mapping for a song with a given band layout.

| Column | Type | Constraints |
|--------|------|-------------|
| id | INTEGER | PRIMARY KEY |
| song_id | INTEGER | FK → Song(id), NOT NULL |
| band_layout_id | INTEGER | FK → BandLayout(id), NOT NULL |
| name | TEXT | NULL |
| created_at | TEXT | NOT NULL |
| updated_at | TEXT | NOT NULL |

---

### SongLayoutAssignment

Maps each player (in band layout) to a part or no part.

| Column | Type | Constraints |
|--------|------|-------------|
| id | INTEGER | PRIMARY KEY |
| song_layout_id | INTEGER | FK → SongLayout(id), NOT NULL |
| player_id | INTEGER | FK → Player(id), NOT NULL |
| part_number | INTEGER | NULL |
| created_at | TEXT | NOT NULL |
| updated_at | TEXT | NOT NULL |

---

## 4. Setlists

### SetlistFolder

Folders for organizing setlists.

| Column | Type | Constraints |
|--------|------|-------------|
| id | INTEGER | PRIMARY KEY |
| name | TEXT | NOT NULL |
| sort_order | INTEGER | NOT NULL DEFAULT 0 |
| created_at | TEXT | NOT NULL |
| updated_at | TEXT | NOT NULL |

---

### Setlist

| Column | Type | Constraints |
|--------|------|-------------|
| id | INTEGER | PRIMARY KEY |
| name | TEXT | NOT NULL |
| band_layout_id | INTEGER | FK → BandLayout(id), NULL |
| folder_id | INTEGER | FK → SetlistFolder(id), NULL |
| sort_order | INTEGER | NOT NULL DEFAULT 0 |
| locked | INTEGER | NOT NULL DEFAULT 0 |
| default_change_duration_seconds | INTEGER | NULL |
| export_naming_rules | TEXT | NULL |
| notes | TEXT | NULL |
| set_date | TEXT | NULL (YYYY-MM-DD) |
| set_time | TEXT | NULL (HH:MM) |
| target_duration_seconds | INTEGER | NULL |
| created_at | TEXT | NOT NULL |
| updated_at | TEXT | NOT NULL |

---

### SetlistItem

Song in a setlist.

| Column | Type | Constraints |
|--------|------|-------------|
| id | INTEGER | PRIMARY KEY |
| setlist_id | INTEGER | FK → Setlist(id), NOT NULL |
| song_id | INTEGER | FK → Song(id), NOT NULL |
| position | INTEGER | NOT NULL |
| override_change_duration_seconds | INTEGER | NULL |
| song_layout_id | INTEGER | FK → SongLayout(id), NULL |
| created_at | TEXT | NOT NULL |
| updated_at | TEXT | NOT NULL |

---

### PlayLog

Play history records.

| Column | Type | Constraints |
|--------|------|-------------|
| id | INTEGER | PRIMARY KEY |
| song_id | INTEGER | FK → Song(id), NOT NULL |
| played_at | TEXT | NOT NULL |
| context_setlist_id | INTEGER | FK → Setlist(id), NULL |
| context_note | TEXT | NULL |
| created_at | TEXT | NOT NULL |

---

### SetlistBandAssignment

Per-setlist-item part overrides (without modifying SongLayout).

| Column | Type | Constraints |
|--------|------|-------------|
| id | INTEGER | PRIMARY KEY |
| setlist_item_id | INTEGER | FK → SetlistItem(id), NOT NULL |
| player_id | INTEGER | FK → Player(id), NOT NULL |
| part_number | INTEGER | NULL |
| created_at | TEXT | NOT NULL |
| updated_at | TEXT | NOT NULL |

---

## 5. Settings & Targets

### AccountTarget

PluginData export targets.

| Column | Type | Constraints |
|--------|------|-------------|
| id | INTEGER | PRIMARY KEY |
| account_name | TEXT | NOT NULL |
| plugin_data_path | TEXT | NOT NULL |
| enabled | INTEGER | NOT NULL DEFAULT 1 |
| created_at | TEXT | NOT NULL |
| updated_at | TEXT | NOT NULL |

---

### FolderRule

Excluded folder rules for library scanning.

| Column | Type | Constraints |
|--------|------|-------------|
| id | INTEGER | PRIMARY KEY |
| rule_type | TEXT | NOT NULL |
| path | TEXT | NOT NULL |
| enabled | INTEGER | NOT NULL DEFAULT 1 |
| include_in_export | INTEGER | NOT NULL DEFAULT 0 |
| created_at | TEXT | NOT NULL |
| updated_at | TEXT | NOT NULL |

---

## Indexes

| Index | Table | Column(s) |
|-------|-------|-----------|
| idx_songfile_song_id | SongFile | song_id |
| idx_song_status_id | Song | status_id |
| idx_playlog_song_id | PlayLog | song_id |
| idx_playlog_played_at | PlayLog | played_at |
| idx_setlistitem_setlist_id | SetlistItem | setlist_id |
| idx_folderrule_rule_type | FolderRule | rule_type |

---

## Internal Tables

### schema_version

Tracks the current migration version. Single row.

| Column | Type | Constraints |
|--------|------|-------------|
| version | INTEGER | PRIMARY KEY |

---

## Migration System

The database tracks its schema version in the `schema_version` table. On startup, `init_database()` ensures the DB is at the current version by running any pending migrations in order.

- **schema_version** table: `version INTEGER PRIMARY KEY` (single row)
- Migrations are numbered 1..N; each upgrades the schema by one version
- A DB with no `schema_version` or version 0 is treated as needing all migrations
- Migrations are idempotent where possible (check before alter) and safe to run on already-upgraded DBs

When adding new migrations:

1. Add a new migration function (e.g. `_migrate_v12_add_foo`)
2. Append it to `_MIGRATIONS` in `schema.py` with the next version number
3. Update `CURRENT_SCHEMA_VERSION`
4. Document the change in this file if it adds tables or columns
