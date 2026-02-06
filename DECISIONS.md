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

## 015 — Set Playback client sync protocol

- **Phase 1 (v1):** LAN-only. Leader runs a WebSocket server; clients connect directly to leader's IP:port (or discover via mDNS). Message format is transport-agnostic (e.g. JSON: set state, highlights) so the same protocol can be used over other transports later.
- **Phase 2 (planned):** Internet-wide Set Playback via a relay. Leader and clients connect to a central relay; same message format. Auth and hosting TBD when Phase 2 is implemented. No relay code in v1.

## 016 — Compatibility support matrix

- Use a **tiered** matrix: **Supported** (tested, we fix bugs), **Best effort** (works in practice, not guaranteed), **Out of scope** (explicitly not supported).
- **Supported:** LOTRO ABC workflow; Maestro-exported tags; Windows, macOS, Linux (current Flet/SQLite stack); local-first, no cloud required.
- **Best effort:** Older or non-Maestro ABC; other games' paths; portable vs installer per platform.
- **Out of scope:** Cloud hosting requirement; other games as primary target. Document tiers in README or a short Compatibility subsection in docs.

## 017 — PlayerInstrument proficiency (per-instrument, binary)

- **Decision:** Proficiency is **per-instrument** (per instrument class) and **binary**: the player either knows how to play that instrument class or they do not.
- If a player has proficiency in an instrument class (e.g. fiddle), they can play **all variants** of that instrument (e.g. lonely mountain fiddle, bardic fiddle, basic fiddle). If they lack proficiency in that class, they cannot play it.
- Stored as **has_proficiency** (BOOLEAN) on PlayerInstrument: true = knows how to play this instrument class (all variants); false = does not. No numeric scale.

## 018 — Status.color

- **Format:** Optional **hex** (e.g. #RRGGBB). Store as TEXT NULL; when NULL, **default to theme** (see 025; UI uses theme default for badges). Not required per status.
- DATA_MODEL: color (TEXT NULL); NULL = default to theme; otherwise hex string.

## 019 — SongFile change detection

- **Decision:** Use **mtime** as the primary change signal. Compute and store **file_hash** (e.g. SHA-256 of content) when feasible; use hash to confirm change when mtime is ambiguous. Do not require hash—mtime-only is allowed; document that hash improves robustness.
- SongFile.file_hash remains optional; scanner should populate it when practical.

## 020 — Set/export folder indexing

- When set/export folders are "included": **index** their files but **suppress** them from the main library view (do not show as duplicates in the library list). Optional setting (e.g. "Show set copies in library") can expose them. Behavior is configurable via FolderRule so per-folder inclusion/suppression is possible.
- Primary library = normal indexing and display; set/export = indexed, suppressed from main view by default.

## 021 — Export metadata to ABC comments

- **Decision:** Deferred to **post–v1**. Not in scope for initial release. When implemented: opt-in only, clearly labeled, with preview and backup (per DECISIONS 006).

## 022 — \*.abcp import/export spec

- Compatibility target remains "ABC Player \*.abcp (Aifel/Elemond)". Spec details will be captured or referenced in docs (e.g. docs/FILE_FORMATS.md or docs/ABCP_SPEC.md) when import/export is implemented. No formal spec in repo until then; REQUIREMENTS/README keep "spec details captured separately" / "exact spec TBD" with a note that the format will be documented when implemented.

## 023 — Setlist.band_layout_id NULL and FolderRule

- **Setlist.band_layout_id NULL:** When NULL, treat the set as **draft**. UI must require the user to choose a band layout before starting Set Playback (or playing the set). No automatic default.
- **FolderRule:** At least one library_root is required for a non-empty library; the app may run with zero roots (empty library—show empty state). FolderRule is recommended for normal use.

## 024 — License and Maestro tag exact patterns

- **License:** Left as **TBD**; to be chosen by the project owner. README continues to list "License: TBD" until a license is selected.
- **Maestro tag exact patterns:** Tags are `%%tag-name` (two percent signs, tag name with hyphen, optional space, then value). Tag names are **case-sensitive** (e.g. %%song-title). Leading/trailing whitespace on the value is trimmed. Exact patterns are specified in docs/FILE_FORMATS.md.

## 025 — Theme definition

- **Theme** is the application’s default visual style: a **dark color scheme** inspired by *The Lord of the Rings* / *Lord of the Rings Online* interfaces.
- Used when Status.color (or other UI elements) is NULL: the UI falls back to theme defaults (e.g. badge colors, backgrounds, text). Implementation defines the exact palette; the overall look should evoke LOTR/LOTRO-style dark UI.
- This project is not affiliated with or endorsed by the owners of those properties; “inspired by” is a visual reference only.

---

## Resolved open decisions
Previously open items have been resolved in ADRs 015–025 above. The only remaining TBD is **License** (024), to be chosen by the project owner.

---


