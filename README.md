# ABC Music Manager

**Version 0.2.5b** — [Changelog](CHANGELOG.md)

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

Open **Help → User Guide** in the app, or see the full guide at [docs/user/index.md](docs/user/index.md).

Quick checklist:

1. **LOTRO folder** — Settings → Folder rules
2. **Account targets** — Settings → Account targets → Scan Account Targets
3. **Scan library** — File → Scan Library
4. **Write PluginData** (optional) — File → Write PluginData…

---

## For developers

See [docs/DEVELOPER.md](docs/DEVELOPER.md) for build instructions, design docs, and contributing.

---

## Legal

ABC Music Manager is a community tool for use with *The Lord of the Rings Online* player music system. It is **not affiliated with, endorsed by, or sponsored by** the game's publisher/developer or the owners of any related trademarks. All trademarks are the property of their respective owners.

**Third-party components:** Qt/PySide6 (LGPL-3.0), Maestro (MIT), LotroInstruments.sf2, and others. See [NOTICE.txt](NOTICE.txt) for full license and attribution details.
