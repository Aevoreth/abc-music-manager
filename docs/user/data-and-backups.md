# Data and backups

ABC Music Manager is **local-first**: your ABC files stay in your Music folders; the app maintains an index and preferences separately.

---

## Data directory

Default location:

`~/.abc_music_manager/`

Typical contents:

- `abc_music_manager.sqlite` — library index, setlists, bands, play history
- `preferences.json` — settings, window layout, relays, filters

Override the location with the **`ABC_MUSIC_MANAGER_DATA`** environment variable (point to a folder path).

---

## What is not stored in the data directory

- Original ABC files (remain under LOTRO Music / your folders)
- Exported set folders (wherever you export them)
- Game PluginData except when you explicitly write plugindata

---

## Backup suggestions

1. Copy the entire `~/.abc_music_manager/` folder periodically
2. Keep your Music library backed up separately
3. Export important setlists via [Set export](set-export.md) for portable copies

---

## Reset preferences

**Settings → Appearance → Reset all preferences** clears settings and restarts the app. This does **not** delete your SQLite library by itself, but paths and filters return to defaults.

---

[← User Guide home](index.md)
