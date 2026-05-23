# Import and export formats

Overview of file formats ABC Music Manager reads and writes.

---

## ABC files

The library indexes standard LOTRO / Maestro ABC files. Common Maestro tags at the top of files:

- `%%song-title`
- `%%song-composer`
- `%%song-duration`
- `%%song-transcriber`
- `%%export-timestamp`

Parts begin at `X:` lines. The scanner stores metadata and part lists in the local database; ABC files remain in your Music folders.

---

## ABCP playlists {#import-abcp}

**Compatibility:** ABC Player (Aifel/Elemond) style `.abcp` XML playlists.

- **Import:** Setlists → **Import ABCP**
- **Export:** Set context menu → **Export to ABCP…**

ABCP stores ordered file paths only — no band layouts, timing, or notes. Paths may be absolute or relative to the playlist location.

---

## Set export packages

Folder or zip export with optional renamed ABC files, part sheets, and CSV. See [Set export](set-export.md).

---

## SongbookData.plugindata

Lua format for the in-game Songbook plugin. See [PluginData / Songbook](plugindata.md).

---

## Relative vs absolute paths

When exporting sets beside ABC files, relative paths help portable folders. Standalone ABCP exports often use absolute paths. Keep playlist and ABC files together when sharing.

---

[← User Guide home](index.md)
