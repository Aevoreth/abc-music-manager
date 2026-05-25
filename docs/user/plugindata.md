# PluginData / Songbook

ABC Music Manager can write **`SongbookData.plugindata`** files for the LOTRO Songbook plugin. There are many compatible versions of Songbook, and this tool should work with them all. This tool is meant to mimic other tools such as Songfiller.hta (ships with most versions of songbook) or tools like Songbooker.

---

## What it is

The file is a **Lua table source** (UTF-8 text) text file stored under `<LOTRO>\PluginData\<AccountName>\AllServers\SongbookData.plugindata`. The Songbook plugin loads it when the plugin is loaded in-game. It is the library that is used by the plugin in order to sync and play music in game. All versions of Songbook are supported.

The app builds the file from your indexed library and configured paths.

---

## Account targets {#account-targets}

Before writing, configure targets under **Settings → Account targets**:

1. Set your LOTRO directory ([Folder rules](settings/folder-rules.md))
2. Click **Scan Account Targets**
3. Enable accounts you want to update

See [Account targets (details)](settings/account-targets.md).

---

## Write PluginData {#write-plugindata}

Choose **File → Write PluginData…**

A log dialog shows progress per account. Errors appear in red.

Re-run after:

- Scanning new music into the library
- Changing folder rules or export paths
- Adding/removing account targets

---

## Export paths

Included directories:

- Your LOTRO Music library, including **Set Export directory**
- Excluded directories only if their **Songbook** column is enabled ([Folder rules](settings/folder-rules.md))

---

[← User Guide home](index.md) · [First-time setup](getting-started.md) · [Import and export](import-export.md)
