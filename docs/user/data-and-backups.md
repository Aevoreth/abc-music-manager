# Data and backups

ABC Music Manager is **local-first**: your ABC files stay in your Music folders; the app maintains an index and preferences separately.

---

## Data directory

Default location of database and preference files are within the release directory itself.

These files are:

- `abc_music_manager.sqlite` — library index, setlists, bands, play history
- `preferences.json` — settings, window layout, relays, filters

---

## What is not stored in the data directory

- Original ABC files (remain under your LOTRO Music folder)
- Exported set folders (wherever you export them)
- Game PluginData (this is written to the PluginData directory directly)

---

## Backup suggestions

1. Copy the entire application folder periodically
2. Keep your Music library backed up separately

---

## Reset preferences

**Settings → Appearance → Reset all preferences** clears settings and restarts the app. This does **not** delete your SQLite library by itself, but paths and filters return to defaults.

---

## Warnings

1. Scanning your library will cause songs that are no longer there to be removed from the database irreversablly (Simply moving or renaming a song within the Music folder will simply update the file path stored unless that song gets moved to an excluded folder)

[← User Guide home](index.md)
