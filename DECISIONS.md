# Architecture Decisions (ADRs-lite) — ABC Music Manager

## 001 — Local-first desktop app
- Decision: The app runs locally as a desktop application.
- Rationale: Users manage local ABC files and typically need low-latency access without a server requirement.

## 002 — Tech stack: Python + Flet + SQLite
- Decision: Use Python with Flet for UI and SQLite for storage.
- Rationale: Cross-platform, fast iteration, and straightforward distribution.

## 003 — Compatibility-first naming
- Decision: Use a product name that does not include specific game branding.
- We avoid using LOTRO or Lord of the Rings Online in the product name to reduce affiliation confusion, while remaining explicitly LOTRO-specific in scope.
- Rationale: Keep the project title general while still supporting game-specific workflows via compatibility features.

## 004 — ABC files are the source of truth
- Decision: The on-disk `.abc` file is the authoritative source of truth for song content and any metadata that is derived from or stored inside the ABC text.
- Rationale: The filesystem is the user’s real library, is shared with other tools, and must remain portable and editable outside the app.

### What this implies
- The database is a **cache + index + app-only metadata store**, not the canonical record of the ABC content.
- On scan/rescan:
  - If the `.abc` file content changes, the app re-parses and updates all derived fields in the DB (e.g., duration, part count, header-based fields).
  - The UI always reflects the latest file state after parsing.

### What is stored in the database
- App-only fields that do not need to be written into the `.abc` file, such as:
  - Rating (0–5)
  - Status label (New/Testing/Ready, etc.)
  - Notes and lyrics (unless explicitly embedded into the ABC by user action)
  - Playback log (PlayLog); last_played_at and total_plays on Song are derived from PlayLog. Play history for a song is derived by table lookup.
  - Song layouts (band layout + player→part mapping) and per-set overrides
- File tracking fields used to detect changes:
  - file_path (unique)
  - mtime and/or content hash

### Editing rules
- If the user edits raw ABC text inside the app, the app writes the `.abc` file and then re-parses it.
- If the user edits a derived field (e.g., title/composer) and that field is sourced from ABC headers, the app updates the ABC header and writes the file (rather than only changing the DB).

### Conflict policy
- If the app has unsaved edits and the underlying `.abc` changes on disk, the app should prevent silent overwrites.
  - Preferred behavior: warn the user and offer options (reload from disk / overwrite / save-as).

## 005 — Title/Composer parsing priority (Maestro comment metadata first)
- Decision: Song Title and Composer will be derived from ABC metadata exported by Maestro that appears in **comments** within the `.abc` file.
- Rationale: Maestro’s exported comment metadata is the most reliable representation of the title/composer the user expects for library management, while `T:` and `C:` fields may be inaccurate for these purposes.

### Parsing priority
1. Maestro-exported comment metadata (exact tag patterns to be specified in docs/FILE_FORMATS.md)
2. `T:` field (fallback)
3. `C:` field (fallback)
4. Filename (final fallback if the above are absent)

### Notes
- The app should store *which source* was used (comment vs header vs filename) to improve transparency and allow future troubleshooting.
- If comment metadata exists, it overrides `T:`/`C:` for display and indexing.

## 006 — App-only metadata is not written back to ABC by default
- Decision: App-only metadata (ratings, statuses, play history, notes/lyrics, band assignments, etc.) will be stored in the database and **will not** be embedded into `.abc` files by default.
- Rationale: Avoid unexpected modifications to users’ libraries and preserve compatibility with other tools and existing workflows.

### Manual write-back
- The app may support an explicit user action to embed selected fields into ABC comments (e.g., via an "Export metadata to comments" command).
- Any such feature must be opt-in, clearly labeled, and ideally support preview + backup.

## 007 — Maestro comment tags are authoritative for song metadata
- Decision: Song-level metadata is parsed from Maestro-exported comment tags when present:
  - `%%song-title`
  - `%%song-composer`
  - `%%song-duration`
  - `%%song-transcriber`
  - `%%export-timestamp`
- Rationale: These tags reflect the values the user expects for library management. ABC header fields like `T:` and `C:` may be present but are not authoritative unless Maestro tags are missing.

### Fallback rules (in priority order)
- Title:
  1) `%%song-title`
  2) first `T:` (fallback)
  3) filename (final fallback)
- Composer(s):
  1) `%%song-composer`
  2) first `C:` (fallback)
  3) Unknown (final fallback)
- Duration:
  1) `%%song-duration` (mm:ss)
  2) Unknown (do not attempt to infer from note data in v1)
- Transcriber:
  1) `%%song-transcriber`
  2) first `Z:` (fallback)
  3) Unknown

## 008 — Composers stored as single text string on Song
- Decision: Composers are stored as a single text field on the Song table (`composers`), not in a normalized Composer table. No comma split between multiple composers—store the value as a single string as parsed from `%%song-composer` / `C:`.
- This is adequate for duplicate detection (normalized title + composers string + part count).

## 009 — Part parsing is block-based; parts stored as JSON on Song
- Decision: A part is defined by each occurrence of `X:` in the file. Part count = total number of `X:` fields.
- For each part block:
  - `X:` value is the **part number**
  - `%%part-name` is the **part name** (as written in ABC)
  - `%%made-for` is matched to an **Instrument** in the instruments table; the part stores **instrument_id** (FK to Instrument.id).
- Storage: Parts are stored in `Song.parts` as a JSON text field: array of `{ part_number, part_name, instrument_id }`. No separate SongPart table.

## 010 — ABC note data is never stored in the database
- Decision: The application does not store musical note bodies from ABC in the DB.
- Rationale: Keeps the DB lightweight and avoids duplicating large text blobs; the `.abc` file remains the source of truth.

## 011 — Duplicate detection and "set folder" handling
- Decision: The scanner distinguishes between:
  - Primary Library files (canonical, indexed normally)
  - Set/Export copies (expected duplicates, indexed optionally and/or suppressed)

### Default behavior
- Files under user-configured "set/export folders" are excluded from normal library indexing by default.
- If set/export files are included, they are flagged as duplicates without prompting unless ambiguity exists.

### Duplicate resolution
- A song’s *logical identity* is defined primarily by:
  - normalized title + composers string (single text; no comma split) + part count
- `%%export-timestamp` is stored as an additional identifier and can help differentiate variants.
- If two primary-library files collide on logical identity:
  - Flag for user resolution: (a) treat as same song variant, (b) keep both as separate songs, (c) ignore one.

## 012 — Playback log; history by table lookup
- Decision: Playback is recorded in a **PlayLog** table (one row per play). There is no play-history JSON on Song.
- Song.last_played_at and Song.total_plays are derived from PlayLog (MAX(played_at) and COUNT respectively). Play history for a song is derived by table lookup (query PlayLog for that song_id, optionally filtered by date range).

## 013 — Song layouts and Instrument catalog
- Decision: A song may have **more than one song layout**. Each song layout references a band layout and contains the part assignments for each player. A song can be used with multiple band configurations via multiple unique song layout entries. No uniqueness constraint on (song_id, band_layout_id).
- Decision: Use **instrument IDs** everywhere. The **Instrument** table contains instrument_id, instrument name, and **alternative instrument names** in a comma-separated list. Song parts reference instrument_id; `%%made-for` in ABC is matched against name or alternative names (or create new instrument). No raw instrument text storage.
- PlayerInstrument links players to instruments (instrument_id) for capability tracking.

## 014 — Set uses single band layout; default part assignments null
- Decision: A setlist is played using a **single band layout** for the entire set. The set has one band_layout_id; song layouts used in the set are based on that band layout. SetlistItem does not have its own band_layout_id.
- Decision: Default values for part assignments (in both setlist and regular song layouts) are **null** (player has no part). In song layout edit mode, a dropdown lists all available parts plus a “None” option to indicate that a player doesn’t have a part in that song (e.g. when the song has fewer parts than band members).
- Decision: When SetlistItem.song_layout_id is NULL, a selection is required—the UI should indicate that the user must choose a song layout (no automatic default).

---

## Open decisions
- Client sync protocol for Set Playback mode (connection model: LAN only? localhost? websockets? built-in Flet multi-user?)
- Formal compatibility support matrix (platforms, file format variants, optional game-specific paths)

---

## Decisions that need to be made

The following are not yet decided; they affect implementation, schema, or product scope.

1. **PlayerInstrument.proficiency** — DATA_MODEL marks this as “scale/enum TBD”. Decide the scale (e.g. 1–5, or labels like beginner / intermediate / advanced) and whether it is optional.

2. **Status.color** — Documented as “implementation-defined” UI token. Decide format (e.g. hex codes, named theme tokens) and whether it is required per status.

3. **SongFile change detection** — `file_hash` is “optional but recommended”. Decide: require content hash for robust change detection, or allow mtime-only and document limitations.

4. **Set/export folder indexing** — When set/export folders are “included”, decide: index files but suppress from main library view only, or index and show as duplicates, or make behavior configurable per folder.

5. **Export metadata to ABC comments** — DECISIONS 006 says the app “may support” an explicit write-back. Decide: in scope for v1 or deferred.

6. **\*.abcp import/export spec** — REQUIREMENTS and README reference ABC Player \*.abcp compatibility with “spec details captured separately” / “exact spec TBD”. Capture or reference the spec so import/export can be implemented.

7. **Setlist.band_layout_id NULL** — Setlist allows band_layout_id NULL. Decide behavior when NULL (e.g. UI must require selection before play, or set is “draft” until layout chosen).

8. **FolderRule** — DATA_MODEL labels FolderRule as “(recommended)”. Decide: is at least one library root required for scanning, or can the app run with no roots (empty library)?

9. **License** — README lists “License: TBD”. Choose license for the project.

10. **Maestro tag exact patterns** — DECISIONS 005 references “exact tag patterns to be specified in docs/FILE_FORMATS.md”. FILE_FORMATS lists tag names; decide whether to specify whitespace/case rules for parsing (e.g. `%%song-title` vs `%% song-title`).
