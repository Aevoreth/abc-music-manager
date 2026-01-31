# Requirements — ABC Music Manager

ABC Music Manager is a local-first desktop application designed specifically for player musicians in The Lord of the Rings Online who manage and perform ABC music libraries. It focuses on: library indexing, metadata parsing, filtering/search, setlist workflows, band layouts, and live set coordination.

---

## 1. Library View

### User Story
As a LOTRO player musician, I want a fast, filterable table of my ABC songs so I can quickly find and manage tracks for practice or performance.

### Acceptance Criteria
- The main Library View displays a table of songs with (at minimum) these fields:
  - Title
  - Composer(s) (comma-separated display, normalized internally)
  - Transcriber
  - Duration (mm:ss)
  - Part Count
  - Last Played (relative time, e.g., "3 days ago")
  - Total Plays
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
- Shows part list (one row per part) with:
  - Part number
  - Part name
  - Made-for instrument
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
- `%%song-composer` (may contain multiple comma-separated composers)
- `%%song-duration` (mm:ss)
- `%%song-transcriber`
- `%%export-timestamp`

#### Fallback behavior (only if Maestro tag is missing)
- Title fallback: first `T:` field, then filename
- Composer fallback: first `C:` field, otherwise "Unknown"
- Transcriber fallback: first `Z:` field, otherwise blank/unknown
- Duration: if missing or unparseable, store as unknown (do not infer from note bodies in v1)

### Composer normalization
- `%%song-composer` can contain multiple composers separated by commas.
- A composer name is normalized by trimming whitespace and collapsing repeated spaces.
- Each distinct composer is stored once in the `Composer` table.
- A song references composers via a join table (many-to-many).

### Part parsing
- Part count is the total number of `X:` fields in the file.
- The number after `X:` is the part number.
- Each part block also includes:
  - `%%part-name` (part name)
  - `%%made-for` (intended instrument)

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
  - normalized title + normalized composer set + part count

- `%%export-timestamp` is stored to help differentiate variants of the same logical identity.

### Default behavior
- Files inside user-configured set/export folders are excluded from the main library by default.
- These files may still be indexed as file-copies for export/import workflows if desired.

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
  - Recording each player’s instruments (possession and proficiency)
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
  - Open and save `*.abcp` files compatible with ABC Player by Aifel and Elemond (spec details captured separately)
  - Export to folder or zip with configurable naming rules
- Per-set configuration:
  - Set selects a band layout default
  - Each song in the set can override part/instrument assignments independent of the library defaults

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
  - Part number (large, bold, centered)
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
