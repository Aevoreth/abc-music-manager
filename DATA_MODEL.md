# Data Model (Draft) — ABC Music Manager

This data model is designed for SQLite and reflects key project decisions:
- `.abc` files on disk are the source of truth for song content and tag-derived metadata.
- Maestro comment tags are authoritative when present.
- Musical ABC note bodies are not stored in the database.
- Song composers are stored as a single text string (no comma split); adequate for duplicate detection.
- Song parts are stored as a JSON text field; each part references an instrument by ID. Instruments have primary name and optional alternative names for matching.
- Songs may have zero or more song layouts; each song layout references a band layout and contains part assignments per player. A song can be used with multiple band configurations via multiple unique song layout entries.
- Playback is recorded in a PlayLog table; play history for a song is derived by table lookup. No play-history JSON on Song.
- A setlist uses a single band layout for the entire set; song layouts in the set are based on that band layout. Default part assignments are null (player has no part).
- Duplicate handling is supported by tracking multiple files per logical song.

---

## 1. Core Entities

### Song
Represents the logical song shown in the library UI (not a specific file copy).

Fields:
- id (INTEGER PK)
- title (TEXT)
- composers (TEXT) — stored as a single text string as parsed from `%%song-composer` / `C:` (no comma split). Kept in sync with the file; adequate for duplicate detection.
- duration_seconds (INTEGER NULL)
- transcriber (TEXT NULL)
- rating (INTEGER NULL) — 0–5
- status_id (INTEGER FK → Status.id, NULL)
- notes (TEXT NULL) — app-only notes (NOT ABC musical notes)
- lyrics (TEXT NULL)
- last_played_at (DATETIME NULL) — derived from PlayLog (most recent play)
- total_plays (INTEGER NOT NULL DEFAULT 0) — derived from PlayLog (count for this song)
- parts (TEXT NULL) — JSON array of part definitions. Each element: `{"part_number": int, "part_name": string|null, "instrument_id": int|null}`. `part_name` from `%%part-name`; `instrument_id` references Instrument.id.
- created_at (DATETIME)
- updated_at (DATETIME)

Notes:
- title / composers / transcriber / duration are generally derived from file tags and kept in sync with the file.
- App-only fields (rating, status, notes, lyrics, play stats) live here. Play history for a song is derived by querying PlayLog.
- Part count = length of `parts` array.

---

### Instrument
Catalog of instruments (e.g. flute, lute, horn). Used to tag which instrument a song part was made for. Matching uses instrument_id everywhere; instrument names (and alternatives) are stored here.

Fields:
- id (INTEGER PK)
- name (TEXT UNIQUE) — primary display name
- alternative_names (TEXT NULL) — comma-separated list of alternative names for matching (e.g. "Lute, lute, theorbos")
- created_at (DATETIME)
- updated_at (DATETIME)

Notes:
- `%%made-for` in ABC is parsed as text and matched against name or alternative_names (or create new instrument) to store `instrument_id` in the song’s `parts` JSON.

---

### SongFile
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

### Status
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

### PlayLog
Playback log. Each row records one play of a song. Play history for a song is derived by table lookup (query PlayLog for that song_id).

Fields:
- id (INTEGER PK)
- song_id (INTEGER FK → Song.id)
- played_at (DATETIME)
- context_setlist_id (INTEGER FK → Setlist.id, NULL)
- context_note (TEXT NULL)
- created_at (DATETIME)

Derived:
- Song.last_played_at = MAX(PlayLog.played_at) for that song.
- Song.total_plays = COUNT(PlayLog) for that song.
- “Plays in last N days” and history views = query PlayLog filtered by song_id and optional date range.

---

## 2. Song Layouts

A song can have zero or more **song layouts**. Each song layout references a band layout and contains the part assignments for each player in that song. In this way a song can be used with multiple band configurations via multiple unique song layout entries.

### SongLayout
One layout configuration for a song: which band layout is used and how players map to parts (or to “no part”).

Fields:
- id (INTEGER PK)
- song_id (INTEGER FK → Song.id)
- band_layout_id (INTEGER FK → BandLayout.id)
- name (TEXT NULL) — optional label, e.g. "Default", "Festival"
- created_at (DATETIME)
- updated_at (DATETIME)

Notes:
- A song may have more than one song layout (e.g. for the same or different band layouts). No uniqueness constraint on (song_id, band_layout_id).

---

### SongLayoutAssignment
Maps each player (in the band layout) to a part in the song’s parts list, or to no part. Default for part assignment is null (player has no part in that song).

Fields:
- id (INTEGER PK)
- song_layout_id (INTEGER FK → SongLayout.id)
- player_id (INTEGER FK → Player.id)
- part_number (INTEGER NULL) — part number in the song’s `parts` array (X: value); NULL = this player has no part (e.g. song has fewer parts than band members)
- created_at (DATETIME)
- updated_at (DATETIME)

Notes:
- One row per player that appears in the band layout. In song layout edit mode, UI shows a dropdown with all available parts plus a “None” option.

---

## 3. Setlists

A setlist is played using a **single band layout** for the entire set. Song layouts used in the set are based on that set’s band layout.

### Setlist
Fields:
- id (INTEGER PK)
- name (TEXT)
- band_layout_id (INTEGER FK → BandLayout.id, NULL) — band layout used for the entire set; song layouts in the set are based on this
- locked (BOOLEAN NOT NULL DEFAULT 0)
- default_change_duration_seconds (INTEGER NULL)
- export_naming_rules (TEXT NULL) — JSON/text blob
- created_at (DATETIME)
- updated_at (DATETIME)

---

### SetlistItem
Represents a song in a setlist. The set’s band layout (Setlist.band_layout_id) applies; no per-item band layout.

Fields:
- id (INTEGER PK)
- setlist_id (INTEGER FK → Setlist.id)
- song_id (INTEGER FK → Song.id)
- position (INTEGER)
- override_change_duration_seconds (INTEGER NULL)
- song_layout_id (INTEGER FK → SongLayout.id, NULL) — which song layout (player→part mapping) to use for this song; must use a SongLayout whose band_layout_id matches the set’s band layout. If NULL, a selection is required (user must choose a song layout).
- created_at (DATETIME)
- updated_at (DATETIME)

---

## 4. Bands & Layouts

### Band
Fields:
- id (INTEGER PK)
- name (TEXT)
- created_at (DATETIME)
- updated_at (DATETIME)

---

### Player
Fields:
- id (INTEGER PK)
- name (TEXT)
- created_at (DATETIME)
- updated_at (DATETIME)

---

### PlayerInstrument
Links a player to an instrument (from the Instrument catalog) and optional proficiency/notes.

Fields:
- id (INTEGER PK)
- player_id (INTEGER FK → Player.id)
- instrument_id (INTEGER FK → Instrument.id)
- has_instrument (BOOLEAN NOT NULL DEFAULT 1)
- proficiency (INTEGER NULL) — scale/enum TBD
- notes (TEXT NULL)
- created_at (DATETIME)
- updated_at (DATETIME)

Notes:
- Uses instrument_id (FK to Instrument). Instrument names and alternative names live in the Instrument table.

---

### BandMember (Join Table)
Maps players to bands.

Fields:
- band_id (INTEGER FK → Band.id)
- player_id (INTEGER FK → Player.id)

Primary Key:
- (band_id, player_id)

---

### BandLayout
Fields:
- id (INTEGER PK)
- band_id (INTEGER FK → Band.id)
- name (TEXT)
- created_at (DATETIME)
- updated_at (DATETIME)

---

### BandLayoutSlot
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

## 5. Setlist Overrides (Per-Set Per-Song)

### SetlistBandAssignment (Per-set/per-song overrides)
Optional overrides when a setlist item should change which part a player plays (without changing the stored SongLayout). Default part assignment is null (no part).

Fields:
- id (INTEGER PK)
- setlist_item_id (INTEGER FK → SetlistItem.id)
- player_id (INTEGER FK → Player.id)
- part_number (INTEGER NULL) — override part for this player for this setlist item; NULL = no part
- created_at (DATETIME)
- updated_at (DATETIME)

---

## 6. Settings & Targets

### AccountTarget
Used for PluginData writing targets.

Fields:
- id (INTEGER PK)
- account_name (TEXT)
- plugin_data_path (TEXT)
- enabled (BOOLEAN NOT NULL DEFAULT 1)
- created_at (DATETIME)
- updated_at (DATETIME)

---

### FolderRule (recommended)
Defines library roots, set/export folders, and exclusions.

Fields:
- id (INTEGER PK)
- rule_type (TEXT) — "library_root" | "set_root" | "exclude"
- path (TEXT)
- enabled (BOOLEAN NOT NULL DEFAULT 1)
- created_at (DATETIME)
- updated_at (DATETIME)

---

## 7. Uniqueness & Duplicate Strategy (Implementation Notes)

### Logical identity (primary heuristic)
- normalized title + Song.composers (single text string; no comma split) + part count. Storing composers as a single string is adequate for duplicate detection.

### Practical behavior
- Many SongFile rows may map to one Song.
- The app should exclude set/export roots from the main library view by default.
- When two primary-library files collide on logical identity:
  - prompt the user to resolve (variants / separate / ignore).
