# ABC Music Manager — Project Brief

## Summary
ABC Music Manager is a locally run desktop application designed specifically for players of The Lord of the Rings Online player music and the users of its surrounding tool/file ecosystem who need a system to manage their ABC music library, setlists/playlists, band layouts, and live set playback coordination.

The app is local-first, indexes ABC files from user-selected folders, and provides fast filtering, playback controls, and event-ready set tools.

## Target Audience
- Player musicians who perform in-game ABC music (soloists, ensembles, band leaders)
- Users with large ABC libraries who need organization, search, and operational tools for live events

## Primary Goals
1. **Library Management**
   - Index and manage a user’s ABC files from local folders
   - Provide a fast, filterable library view with rich metadata and editing
2. **Band & Setlist Management**
   - Define band rosters, player capabilities, and layout(s)
   - Create and manage setlists/playlists and per-set/per-song configurations
3. **Live Playback Coordination**
   - Provide a "Set Playback" mode for a band leader to run a show
   - Allow one or more clients to connect and view live set status and band layout updates
4. **SongbookData.plugindata Generation (Game Compatibility Feature)**
   - Write SongbookData.plugindata (JSON) to selected game account PluginData directories (where applicable)
   - Reduce the need for separate external utilities that generate the same file

## Non-Goals (initially)
- Cloud hosting or remote web service requirement (local-first)
- Automatic/continuous SongbookData.plugindata writing (manual initiation initially)
- Full DAW-style editing tools (beyond basic ABC editing and metadata management)

## Key Modules
- Library View + Song Detail/Edit
- ABC Playback (multi-part, mute/solo)
- Band Management (grid layout + player cards)
- Setlist Manager (drag/drop, export/import ABP/ABCP-like)
- Set Playback Mode (leader + client view)
- Settings (paths, exclusions, plugin data targets, statuses, soundfont config)
- Filesystem Watcher (quiet background rescan)

## Tech Stack (proposed)
- **Python + PySide6 (Qt for Python)** — desktop UI with native theming and styling
- SQLite database
- Cross-platform (Windows/Mac/Linux)
- Portable or installable distribution

## Open Questions / Decisions Needed
See DECISIONS.md for "Open decisions" and "Decisions that need to be made". Key open items include (many design choices are already in DECISIONS.md):
- Client connection model for Set Playback mode (LAN only? localhost? websockets? built-in Flet multi-user?)
- ABC parsing expectations (what metadata is read from files vs. derived vs. user-entered)
- Source of truth rules when ABC file changes on disk (merge strategy vs. overwrite)
- Compatibility scope: which games/tools/formats are explicitly supported vs “best effort”
