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

## Storage rules
- Musical note bodies from ABC are not stored in the database.
- The `.abc` file remains the source of truth for song content and tag-derived metadata.
- Song composers are stored as a single text string (no comma split).
- Song parts are stored as a JSON text field on the song; each part references an instrument by id. Instruments table has name and alternative_names (comma-separated) for matching.
