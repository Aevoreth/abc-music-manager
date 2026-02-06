# ABC Music Manager

ABC Music Manager is a local-first desktop application designed specifically for player musicians in *The Lord of the Rings Online* who manage and perform ABC music libraries. It helps you organize a large ABC library, build and run event setlists, model band layouts, preview multi-part playback, and generate `SongbookData.plugindata` for selected accounts.

> **Status:** Early design / in active development. The UI is being rebuilt with **PySide6 (Qt)**; previous Flet code is in `/old/` (see DECISIONS 026).  
> **License:** TBD (to be chosen by project owner — DECISIONS 024)
> **Disclaimer:** Not affiliated with or endorsed by the creators/publishers of *The Lord of the Rings Online*.

---

## What it does

### Compatibility (DECISIONS 016)
- **Supported:** LOTRO ABC workflow; Maestro-exported tags; Windows, macOS, Linux; local-first, no cloud required.
- **Best effort:** Older or non-Maestro ABC; other games' paths; portable vs installer per platform.
- **Out of scope:** Cloud hosting requirement; other games as primary target.

### Library Management
- Indexes ABC files from user-selected folders
- Fast, filterable library view with columns like:
  - Title, composer(s), duration, part count
  - Last played, play count, play history (from playback log), rating, status badges
  - Notes and lyrics
- Song detail/edit screen:
  - Edit metadata
  - Optional raw ABC editing

### ABC Playback
- Playback using a configurable soundfont intended to match common community workflows/tools
- Shows all parts
- Mute/solo one or more parts during playback

### Band Management
- Band roster with player instrument capabilities (possession + per-instrument proficiency: can play instrument class and all variants, e.g. all fiddles, or cannot)
- Drag/drop band layout editor on a snapped grid
- Player cards are **7 grid units wide × 5 grid units tall**
- Band layouts can be reused across songs and setlists; songs can have multiple song layouts (band layout + player→part mapping). A set uses one band layout for the entire set; default part assignments are null (dropdown includes “None”).

### Setlist / Playlist Manager
- Build and edit setlists for events
- Add songs from Library View via context menu
- Drag/drop in a compact library view
- Reorder set entries via drag/drop
- Lead-in / song change timing:
  - Default per set
  - Per-song overrides
- Import/export:
  - Open/save `*.abcp` (ABC Player compatibility; spec to be documented when import/export is implemented — DECISIONS 022)
  - Export to folder or zip with configurable naming rules

### Set Playback Mode (Live) (DECISIONS 015)
- **v1:** LAN-only; leader runs WebSocket server; clients connect to leader. **Planned:** internet-wide via relay (same message format).
- Band leader runs the show; clients can connect to view live set status
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

## Running the app

1. **Create a virtual environment** (recommended):
   ```bash
   python -m venv .venv
   .venv\Scripts\activate   # Windows
   # source .venv/bin/activate  # macOS/Linux
   ```
2. **Install dependencies:** `pip install -r requirements.txt` (PySide6 and other deps)
3. **Run:** `python main.py` (entry point to be added with Qt UI)

The database will be created automatically on first run (path TBD with Qt app). The previous Flet app’s CLI init lived at `python -m src.abc_music_manager.cli_init_db` (see `/old/`).

---

## Design Docs (Source of Truth)

- `PROJECT_BRIEF.md` — product goals, scope, modules
- `REQUIREMENTS.md` — user stories + acceptance criteria
- `DATA_MODEL.md` — draft entities/relationships
- `DECISIONS.md` — major architectural decisions (ADRs 001–025; previously open items resolved)

---

## Tech Stack (Planned)
- **Python + PySide6 (Qt for Python)** — desktop UI with full theming and native look-and-feel
- SQLite (database)
- **Theme:** Dark color scheme inspired by *The Lord of the Rings* / *Lord of the Rings Online* interfaces (DECISIONS 025)
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
