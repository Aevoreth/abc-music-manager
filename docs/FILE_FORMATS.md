# File Formats — ABC Music Manager

## Maestro Song Tags (Authoritative)

Parsed from the top-level of the ABC file. **Exact pattern:** `%%tag-name` (two percent signs, tag name with hyphen, optional space after tag name, then value). Tag names are **case-sensitive** (e.g. `%%song-title`). Leading/trailing whitespace on the value is trimmed (DECISIONS 024).

- `%%song-title       <title>`
- `%%song-composer    <composer1>, <composer2>, ...`
- `%%song-duration    <mm:ss>`
- `%%song-transcriber <name>`
- `%%export-timestamp <YYYY-MM-DD HH:MM:SS>`

### Composer storage
- Composers are stored as a single text string (no comma split). The value from `%%song-composer` or `C:` is stored as-is. Adequate for duplicate detection.

## Parts (Block parsing)
A part begins at a line matching `X:\s*<number>` and continues until the next `X:` line or EOF.

Within each block:
- `X:` → part_number
- `%%part-name` → part_name (optional; stored as written)
- `%%made-for` → matched to an instrument by name or alternative names (instruments table: name + comma-separated alternative_names); stored as instrument_id in the song’s parts list (optional)

Part count = total number of `X:` occurrences. Parts are stored on the song as a JSON array: `{ part_number, part_name, instrument_id }`.

## ABCP Playlist Format (ABC Player)

Compatibility target: ABC Player by Aifel/Elemond (DECISIONS 022).

ABCP files are XML playlists containing only ordered track paths. No metadata (band layout, part assignments, notes, timing) is stored.

### Structure

- Root: `<playlist fileVersion="3.4.0.300">`
- Child: `<trackList>` containing `<track>` elements
- Each track: `<track><location>path_to.abc</location></track>` — typically an **absolute** path for a standalone export; **relative** paths (same folder as the `.abcp` file) when the playlist is bundled with the ABC files (set export folder or zip).
- Encoding: UTF-8

### Example

```xml
<?xml version="1.1" encoding="UTF-8" standalone="no"?>
<playlist fileVersion="3.4.0.300">
    <trackList>
        <track>
            <location>C:\path\to\song.abc</location>
        </track>
    </trackList>
</playlist>
```

Relative locations (set export): e.g. `<location>001_My_Song.abc</location>` next to `{set_name}.abcp` inside the exported folder or zip.

### Import/Export notes

- **Import:** Paths must match library SongFile paths (exact match). Unmatched paths are skipped; user is informed.
- **Export (setlist → ABCP file):** Uses primary file path per song. Band layout, part assignments, notes, timing, and other metadata are not included.
- **Set export (folder/zip):** Optional (same dialog as CSV). When enabled, writes `{set_name}.abcp` beside the copied ABC files with **relative** paths so ABC Player can open the playlist from the bundle.

---

## SongbookData.plugindata (Songbook plugin)

`SongbookData.plugindata` is **UTF-8 text** containing **Lua** data: a top-level `return` statement and a table literal (it is **not** JSON). The LOTRO Songbook plugin reads this file from the account PluginData directory.

### Structure

- Root table keys: `Directories`, `Songs`.
- **Directories:** array-style table mapping integer → string. Each value is a path relative to the game `\Music\` folder, forward slashes only, with a trailing `/` on directory paths (e.g. `/Band/Sets/`). Includes `/` and every ancestor path that contains at least one listed song.
- **Songs:** array-style table mapping integer → song table:
  - `Filepath` — directory part (same rules as Directories)
  - `Filename` — ABC file stem (no `.abc` suffix in the file)
  - `Tracks` — array-style table of `{ Id, Name }` (part id string and display name for the Songbook UI)
  - `Transcriber`, `Artist` — strings

Which ABC files are included follows the app’s music root, set export directory, and Songbook exclude rules. Authoritative builder: `src/abc_music_manager/services/plugindata_writer.py` (`build_plugindata_lua`). Example output: `files/samples/SongbookData/SongbookData.plugindata`.

---

## Storage rules
- Musical note bodies from ABC are not stored in the database.
- The `.abc` file remains the source of truth for song content and tag-derived metadata.
- Song composers are stored as a single text string (no comma split).
- Song parts are stored as a JSON text field on the song; each part references an instrument by id. Instruments table has name and alternative_names (comma-separated) for matching.
