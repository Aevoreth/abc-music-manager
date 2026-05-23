# Library

The **Library** page is your main song browser: filter, sort, play, edit metadata, and add songs to setlists.

---

## Library table columns

| Column | Description |
|--------|-------------|
| *(Play)* | Start playback (replaces current playlist with this song) or Add to Queue (adds song to end of queue) |
| **Title** | Song title (from ABC / Maestro tags) |
| **Composer(s)** | Composer line |
| **Duration** | Length (mm:ss) |
| **Last played** | Most recent play log entry, listed as X (time) ago |
| **Playback History** | Quick actions: set play time, mark played now, open history log |
| **Parts** | Number of ABC parts (Hover over number to see part numbers and names) |
| **Rating** | Click stars to set 1–5 (click again to clear) |
| **Set** | Shows if song is in an upcoming set; click to jump to setlist |
| **Status** | Custom status badge; click to change (custom statuses added in settings) |
| **Transcriber** | Name of the person/player who transcribed the song |
| **Actions** | **Edit** (song detail) and **Layout** (song layout menu (currently bugged)) |

Click column headers to sort (where supported).

---

## Filters {#filters}

### Main filter row

- **Title / Composer** — text search, searches both fields
- **Status** — chip picker for one or more statuses
- **In set** — Yes / No / Either
- **Rating** — from / to range
- **More Filters** — expands extra options
- **Reset Filters** — restore defaults from [Default filters settings](settings/default-filters.md)
- **Clear Filters** — show everything (most permissive)

### More Filters panel

- **Duration** — min/max range
- **Last played** — time or date range
- **Parts** — min/max part count
- **Transcriber** — chip picker

If the table looks empty, try **Clear Filters** before assuming the library has no songs. You may need to adjust your [Default Filters](settings/default-filters.md) in such a case.

---

## Inline actions

- **Play column** — starts playback
- **Playback History → Now** - Set playback to current time
- **Playback History → Set…** - Set most recent playback time to a specific time
- **Playback History → History…** - Open the playback history panel
- **Rating stars** — set rating in place
- **Set column** — menu to open containing setlist(s)
- **Status column** — pick a status from your configured list
- **Actions → Edit** — open [Song detail](song-detail-and-layouts.md)
- **Actions → Layout** — create or edit [song layouts](song-detail-and-layouts.md#song-layouts)

---

## Context menu

Right-click a row:

- **Add to queue** — append to the playback playlist without stopping current play
- **Add to Set** — add to an unlocked setlist

---

## Empty library state {#empty-library}

If no songs match your filters, you see an empty-state message with an **Open User Guide** button.

If you truly have no indexed songs, follow [First-time setup](getting-started.md#getting-started-checklist).

---

## Double-click

Double-click a row to open **Song detail**.

---

## Play history

From the Library **Playback History** column you can:

- Mark a song as played now
- Set last played to a specific time
- Open full play history editor

Song detail also exposes play history actions. Set Play can auto-log plays when advancing songs ([Set Play](set-play.md)).

---

[← User Guide home](index.md) · [Playback](playback.md) · [Setlists](setlists.md)
