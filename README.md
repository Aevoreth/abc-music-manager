# ABC Music Manager

ABC Music Manager is a local-first desktop application designed specifically for player musicians in *The Lord of the Rings Online* who manage and perform ABC music libraries. It helps you organize a large ABC library, build and run event setlists, model band layouts, preview multi-part playback, and generate `SongbookData.plugindata` for selected accounts.

> **Status:** Early design / in active development  
> **License:** TBD
> **Disclaimer:** Not affiliated with or endorsed by the creators/publishers of *The Lord of the Rings Online*.

---

## What it does

### Compatibility
- **Supported:** *The Lord of the Rings Online* ABC player music workflow
- **Not supported:** Other games / general ABC ecosystems (out of scope)

### Library Management
- Indexes ABC files from user-selected folders
- Fast, filterable library view with columns like:
  - Title, composer(s), duration, part count
  - Last played, play count, rating, status badges
  - Notes and lyrics
- Song detail/edit screen:
  - Edit metadata
  - Optional raw ABC editing

### ABC Playback
- Playback using a configurable soundfont intended to match common community workflows/tools
- Shows all parts
- Mute/solo one or more parts during playback

### Band Management
- Band roster with player instrument capabilities (possession + proficiency)
- Drag/drop band layout editor on a snapped grid
- Player cards are **7 grid units wide × 5 grid units tall**
- Band layouts can be reused across songs and setlists

### Setlist / Playlist Manager
- Build and edit setlists for events
- Add songs from Library View via context menu
- Drag/drop in a compact library view
- Reorder set entries via drag/drop
- Lead-in / song change timing:
  - Default per set
  - Per-song overrides
- Import/export:
  - Open/save `*.abcp` (compatibility target; exact spec TBD)
  - Export to folder or zip with configurable naming rules

### Set Playback Mode (Live)
- “Band leader” runs the show; clients can connect to view live set status
- Highlights:
  - Last played song (green)
  - Next selected song (blue)
- Band layout view shows per player:
  - Name (top), part number (large/bold center), instrument (bottom)
  - Instrument change indicator (gold) when instrument differs from previous song
- Per-client highlight: each viewer can highlight selected players

### Compatibility Feature: `SongbookData.plugindata`
- Manual generation/writing of `SongbookData.plugindata` (JSON) to selected account PluginData directories (where applicable)
- Intended to replace separate utilities that perform the same operation

---

## Design Docs (Source of Truth)

- `PROJECT_BRIEF.md` — product goals, scope, modules
- `REQUIREMENTS.md` — user stories + acceptance criteria
- `DATA_MODEL.md` — draft entities/relationships
- `DECISIONS.md` — major architectural decisions and open questions

---

## Tech Stack (Planned)
- Python + Flet (UI)
- SQLite (database)
- Cross-platform: Windows / macOS / Linux
- Portable or installable distribution

---

## Roadmap (High-Level)
1. Library scanning + DB indexing + Library View filters
2. Song detail/edit + raw ABC editor (optional)
3. Playback engine + part mute/solo
4. Band layout editor + player/instrument modeling
5. Setlist manager (drag/drop, timing, export)
6. Set Playback mode (leader + clients)
7. Manual `SongbookData.plugindata` writer + settings UI
8. Polish, performance tuning, packaging

---

## Contributing (Future)
Contribution guidelines, issue templates, and dev setup instructions will be added once the project structure stabilizes.

---

## Legal / Attribution
ABC Music Manager is a community tool created for use with *The Lord of the Rings Online* player music system.
It is **not affiliated with, endorsed by, or sponsored by** the game's publisher/developer or the owners of any related trademarks.
All trademarks are the property of their respective owners.
