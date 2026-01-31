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
  - Play history (last played, total plays, play log)
  - Per-song band layout assignments and per-set overrides
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

## 008 — Composer normalization and many-to-many relationship
- Decision: Composers are normalized into a `Composer` table. Songs reference composers via a join table (many-to-many).
- Parsing: `%%song-composer` may contain multiple composers separated by commas.
  - Split on commas only (do not split on the word "and").
  - Trim whitespace around each name.
  - De-duplicate composer entries by normalized name.

## 009 — Part parsing is block-based and derived from X-sections
- Decision: A “part” is defined by each occurrence of `X:` in the file.
- Part count = total number of `X:` fields in the file.
- For each part block:
  - `X:` value is the **part number**
  - `%%part-name` is the **part name**
  - `%%made-for` is the **intended instrument**

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
  - normalized title + normalized composer set + part count
- `%%export-timestamp` is stored as an additional identifier and can help differentiate variants.
- If two primary-library files collide on logical identity:
  - Flag for user resolution: (a) treat as same song variant, (b) keep both as separate songs, (c) ignore one.

## Open decisions
- Client sync protocol for Set Playback mode
- Formal compatibility support matrix (platforms, file format variants, optional game-specific paths)
