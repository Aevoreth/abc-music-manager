# File Formats — ABC Music Manager

## Maestro Song Tags (Authoritative)
Parsed from the top-level of the ABC file:

- `%%song-title       <title>`
- `%%song-composer    <composer1>, <composer2>, ...`
- `%%song-duration    <mm:ss>`
- `%%song-transcriber <name>`
- `%%export-timestamp <YYYY-MM-DD HH:MM:SS>`

### Composer parsing
- Split composers on commas only.
- Trim whitespace around each entry.
- Do not split on the word "and".

## Parts (Block parsing)
A part begins at a line matching `X:\s*<number>` and continues until the next `X:` line or EOF.

Within each block:
- `X:` → part_number
- `%%part-name` → part_name (optional)
- `%%made-for` → made_for (optional)

Part count = total number of `X:` occurrences.

## Storage rules
- Musical note bodies from ABC are not stored in the database.
- The `.abc` file remains the source of truth for song content and tag-derived metadata.
