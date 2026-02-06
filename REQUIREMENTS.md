# Requirements — ABC Music Manager

ABC Music Manager is a local-first desktop application designed specifically for player musicians in The Lord of the Rings Online who manage and perform ABC music libraries. It focuses on: library indexing, metadata parsing, filtering/search, setlist workflows, band layouts, and live set coordination.

---

## 1. Library View

### User Story
As a LOTRO player musician, I want a fast, filterable table of my ABC songs so I can quickly find and manage tracks for practice or performance.

### Acceptance Criteria
- The main Library View displays a table of songs with (at minimum) these fields:
  - Title
  - Composer(s) (stored as single text string on song; display as stored)
  - Transcriber
  - Duration (mm:ss)
  - Part Count
  - Last Played (relative time, e.g., "3 days ago")
  - Total Plays
  - Play history (derived from playback log; available on song detail via table lookup)
  - Rating (0–5 stars)
  - Status (configurable label with a color-coded badge, e.g., New/Testing/Ready)
  - In Upcoming Set (indicator)
  - Notes (button/icon)
  - Lyrics (button/icon)

- The Library View supports filtering and searching by:
  - Title search (substring match)
  - Composer search (matches any composer on the song)
  - Transcriber search
  - Duration range
  - Rating range
  - Frequency of play within a timeframe (e.g., plays in last N days/weeks)
  - Status (one or more)
  - Part count (range or exact)
  - (Future) instrument used / “made-for” instrument

- Selecting a song opens Song Detail/Edit.

### Song Detail/Edit Acceptance Criteria
- Shows parsed and stored metadata:
  - Title, composers, transcriber, duration, export timestamp (if available), part count
- Shows part list (from song’s stored parts: one row per part) with:
  - Part number
  - Part name (as in ABC)
  - Made-for instrument (resolved from instrument_id; instruments catalog has name and alternative names for matching)
- Allows editing of:
  - App-only fields: rating, status, notes, lyrics
- Provides an advanced mode to edit raw ABC text (in-file editing):
  - If raw ABC is edited and saved, the app writes the file to disk and re-parses it immediately.
- The app must not store musical ABC note bodies in the database.

---

## 2. Parsing Rules (File Format Contract)

### Authoritative Song Tags (Maestro comment metadata)
The app parses these song-level fields from Maestro comment tags:
- `%%song-title`
- `%%song-composer` (stored as single text string on song; no comma split)
- `%%song-duration` (mm:ss)
- `%%song-transcriber`
- `%%export-timestamp`

#### Fallback behavior (only if Maestro tag is missing)
- Title fallback: first `T:` field, then filename
- Composer fallback: first `C:` field, otherwise "Unknown"
- Transcriber fallback: first `Z:` field, otherwise blank/unknown
- Duration: if missing or unparseable, store as unknown (do not infer from note bodies in v1)

### Composer storage
- Composers are stored as a single text string on the song. No comma split between multiple composers—store the value as a single string. This is adequate for duplicate detection.

### Part parsing
- Part count is the total number of `X:` fields in the file.
- The number after `X:` is the part number.
- Each part block also includes:
  - `%%part-name` (part name)
  - `%%made-for` (intended instrument; matched to instruments catalog by name or alternative names, stored as instrument_id)
- Parts are stored on the song as a JSON list (part number, part name, instrument_id). Instruments table has instrument_id, name, and alternative names (comma-separated).

### Storage rule
- Musical note content is never stored in the DB.
- The `.abc` file is the source of truth for song content and any metadata that exists in the file.

---

## 3. Filesystem Scanning & Sync

### User Story
As a local-first user, I want the app to scan my ABC library folders and keep the index up to date when files change.

### Acceptance Criteria
- Settings allow configuration of:
  - LOTRO base folder (optional convenience)
  - Music folder (library root) or multiple roots
  - Excluded folders
  - Set/export folders (where duplicates are expected)
  - Account targets for PluginData writing

- The app scans configured folders for `.abc` files and maintains an index in SQLite.
- If possible, scanning is supplemented by filesystem watching for low-latency updates with low resource usage.
- The scanner detects changes using mtime and/or content hash and re-parses changed files.
- On re-parse, derived values (duration seconds, part count, title/composer/transcriber from tags) update to match the file.

---

## 4. Duplicate Detection & Resolution

### Definitions
- A song’s *logical identity* is primarily:
  - normalized title + song’s composers (single text string; no comma split) + part count

- `%%export-timestamp` is stored to help differentiate variants of the same logical identity.

### Default behavior
- Files inside user-configured set/export folders are excluded from the main library view by default. When "included," they are indexed but suppressed from the main library list; optional setting can expose them (DECISIONS 020).

### When duplicates occur in primary library roots
If two primary-library files collide on logical identity:
- The app flags the collision and prompts the user to choose:
  1) Treat as variants of the same song (recommended)
  2) Keep as separate songs
  3) Ignore one file

---

## 5. Band Management

### User Story
As a band leader, I want to model my band roster and layout so I can assign parts/instruments realistically.

### Acceptance Criteria
- Band Management supports:
  - Creating a band
  - Adding players
  - Recording each player’s instruments (possession and per-instrument proficiency: can play instrument class and all variants, e.g. all fiddles, or cannot)
- Band Layout Editor:
  - Drag/drop player cards onto a snapped grid
  - Player card size: 7 grid units wide × 5 grid units tall
  - Save multiple layouts per band

---

## 6. Setlist / Playlist Manager

### User Story
As a band leader, I want to build and edit setlists so I can run live events smoothly.

### Acceptance Criteria
- Create/edit/delete setlists
- Add songs to setlists from Library View via context menu:
  - Right-click → Add to Set → <set name>
- Locked sets:
  - Cannot be edited
  - Do not appear in the add-to-set menu
- Drag/drop support:
  - Drag from compact library browser into setlist
  - Reorder setlist items via drag/drop
- Timing:
  - Configurable song-change duration for the set
  - Per-song overrides
- Import/export:
  - Open and save `*.abcp` files compatible with ABC Player by Aifel and Elemond (spec to be documented in docs when import/export is implemented — DECISIONS 022)
  - Export to folder or zip with configurable naming rules
- Per-set configuration:
  - A set uses a single band layout for the entire set. When a set has no band layout selected (draft), the UI requires selection before play (DECISIONS 023). Song layouts in the set are based on that band layout.
  - Each song can have zero or more song layouts (band layout + mapping of player→part). Setlist items must have a song layout selected; when none is selected, the UI indicates that a selection is required.
  - Default part assignments are null (player has no part). In song layout edit mode, a dropdown lists all available parts plus a “None” option for players who don’t have a part in that song (e.g. fewer parts than band members).

---

## 7. Set Playback Mode (Live)

### User Story
As a band leader, I want a live playback coordination screen so I can manage the event and communicate upcoming changes.

### Acceptance Criteria
- Leader view shows:
  - Current/selected next song: title, composer(s), duration, lead-in timing
  - Last played song highlighted (green)
  - Next selected song highlighted (blue)
- Shows band roster list
- Per-client highlighting:
  - Each connected client can highlight one or more players in the layout view
- Band layout view for the next song shows, per player card:
  - Player name (top)
  - Part number (large, bold, centered), or “None” when the player has no part assignment for that song
  - Instrument name (bottom)
- Instrument change indicator:
  - Part number and instrument name are gold if the instrument differs from the previous song for that player

---

## 8. PluginData Writing (SongbookData.plugindata)

### User Story
As a LOTRO player, I want the app to generate `SongbookData.plugindata` so I can avoid separate utilities.

### Acceptance Criteria
- Settings allow choosing one or more account PluginData target directories.
- Writing is initiated manually (not automatic).
- The app writes `SongbookData.plugindata` in JSON format consistent with expected LOTRO plugin consumption.

---

## 9. Non-Functional Requirements
- Performance: library filtering/search should feel instant for large libraries.
- Stability: avoid silent overwrites on file changes.
- Safety: raw ABC editing should be guarded (backup/confirmations recommended).
- Portability: installable or portable distribution across Windows/macOS/Linux.
