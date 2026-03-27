# ABC Music Manager

**Version 0.1.8b** — [Changelog](CHANGELOG.md)

ABC Music Manager is a local-first desktop application for *The Lord of the Rings Online* player musicians who manage ABC music libraries. Organize your library, build setlists for events, model band layouts, preview multi-part playback, and generate Songbook data files for your game accounts.

> **License:** MIT (see [LICENSE.txt](LICENSE.txt))  
> **Source Code:** [Github - Aevoreth/abc-music-manager](https://github.com/Aevoreth/abc-music-manager)  
> **AI assistance:** Created and maintained with substantial help from AI coding tools (large language models); human maintainers own review, testing, and releases.  
> **Disclaimer:** Not affiliated with or endorsed by the creators/publishers of *The Lord of the Rings Online*.

---

## Quick start

- **Built executable:** Double-click the app or run it from the command line.
- **From source:** Run `python main.py` from the repository root (after `pip install -r requirements.txt`).

Your data (library index, preferences) is stored at `~/.abc_music_manager/` (or `$HOME/.abc_music_manager` on macOS/Linux). You can override this with the `ABC_MUSIC_MANAGER_DATA` environment variable.

---

## Getting started

1. **Add your LOTRO folder** — Go to Settings > "Folder Rules" and set your LOTRO data folder (default "C:\Users\<usernam>\Documents\The Lord of the Rings Online\" on Windows). This may already be detected for you.
2. **Set Export directory** - Settings > "Folder Rules" This folder is not scanned by the library scanner (to prevent duplicates) but is included when generating Songbook Data. You may also wish to add excluded directories on the same tab.
3. **Set Account Targets** - Settings > "Account Targets" Here, you can click on "Scan Account Targets". If your LOTRO folder is properly selected, this will scan the PluginData folder within and generate a target for saving Songbook data for each account you have.
4. **Populate your Library** — Run File > Scan Library to index your files. You will need to do this whenever you add new music to your library.

---

## Features

- **Library** — Filterable table of songs with title, composer, duration, part count, ratings, play history. Edit metadata and optionally edit raw ABC text (Advanced users only!).
- **Playback** — Listen to songs using Maestro's provided soundfont (automatically located with new versions of Maestro, can be automatically downloaded if not found). Mute or solo individual parts. Stereo playback supported using song layouts or user pan definitions from Maestro.
- **Bands** — Define players and instruments. Create band layouts with drag-and-drop positioning.
- **Setlists** — Build setlists for events. Add songs from the library, reorder, set instrument changeover timing. Export to folder or zip. Import/export ABCP playlist files from Maestro/ABCPlayer.
- **PluginData** — Generate `SongbookData.plugindata` for selected LOTRO account directories (File > Write PluginData).

---

## For developers

See [docs/DEVELOPER.md](docs/DEVELOPER.md) for build instructions, design docs, and contributing.

---

## Legal

ABC Music Manager is a community tool for use with *The Lord of the Rings Online* player music system. It is **not affiliated with, endorsed by, or sponsored by** the game's publisher/developer or the owners of any related trademarks. All trademarks are the property of their respective owners.

**Third-party components:** Qt/PySide6 (LGPL-3.0), Maestro (MIT), LotroInstruments.sf2, and others. See [NOTICE.txt](NOTICE.txt) for full license and attribution details.
