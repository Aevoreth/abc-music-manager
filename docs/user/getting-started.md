# First-time setup

This guide walks through the minimum steps to get ABC Music Manager indexing your music and ready to use.

---

## Install and launch
- **Download the App:** Go to [ABC Music Manager Releases on Github](https://github.com/Aevoreth/abc-music-manager/releases) and download the latest build or source package.
- **Built executable:** Run `ABC Music Manager.exe` from your release folder.
- **From source:** Install dependencies (`pip install -r requirements.txt`), then run `python main.py` from the repository root.

Your app data (library database, preferences) is stored in the release directory as abc_music_manager.sqlite and preferences.json. Keep these files safe and backed up (especially the sqlite database file).

---

## Getting started checklist {#getting-started-checklist}

### 1. Set your LOTRO directory {#lotro-directory}

Go to **Settings → Folder rules** and set **Lord of the Rings Online directory**.

This is usually something like:

`C:\Users\<you>\Documents\The Lord of the Rings Online\`

The app may auto-detect this path on first run. This folder contains your **Music** library and **PluginData** for Songbook files, as well as game settings, screenshots, and any other data the game needs to run.

→ [Folder rules (details)](settings/folder-rules.md)

### 2. Set Export directory (recommended)

On the same **Folder rules** tab, set **Set Export directory** if you export sets to a dedicated folder.

That folder is **not** scanned for the library (to avoid duplicate entries) but will be included when writing Songbook data.

### 3. Extra Folder rules

Again, on the **Folder rules** tab, you may choose to configure additional folder excludes to prevent certain folders from being scanned into the library. These excludes may optionally be included in Songbook data export passes.

→ [Folder rules → Exclude Rules](settings/folder-rules.md#excluded-directories)

### 4. Configure account targets {#account-targets}

Go to **Settings → Account targets** and click **Scan Account Targets**.

If your LOTRO folder is set correctly, the app finds each game account under PluginData and creates a target for writing `SongbookData.plugindata`.

Enable the accounts you want to update (all are enabled by default).

→ [Account targets (details)](settings/account-targets.md)

### 5. Scan your library {#scan-library}

Choose **File → Scan Library**.

The scanner indexes ABC files from your LOTRO Music folder (and other configured paths). Re-scan whenever you add new music. Note that this process may take a few moments to complete, especially if you have a very large library.

→ [Duplicates and maintenance](duplicates-and-library-maintenance.md) if scan reports duplicates.

### 6. Verify playback {#first-playback}

Open the **Library** page and click **Play** on a song.

ABC Music Manager utilizes the lotroinstruments.sf2 soundfont provided by the Maestro project. If you have Maestro installed vis the MSI package, ABC Music Manager should detect it automatically. If no soundfont is configured, you may be prompted to download or browse for it. See [ABC Playback settings](settings/abc-playback.md).

→ [Playback toolbar](playback.md)

### 7. Write PluginData (optional)

When your library looks correct, use **File → Write PluginData…** to update Songbook files for enabled accounts. This feature is intended to replace Songfiller.hta or Songbooker.

→ [PluginData / Songbook](plugindata.md)

---

## What to do next

| Goal | Start here |
|------|------------|
| Rate and Categorize songs using ratings and statuses | [Library](library.md) + [Statuses](settings/statuses.md) |
| Build a show setlist | [Setlists](setlists.md) |
| Assign parts to band members | [Bands](bands.md) + [Song layouts](song-detail-and-layouts.md) |
| Run a live event | [Set Play](set-play.md) |
| Share set play status with bandmates | [Band Assistant](band-assistant.md) + [Set Playback relays](settings/set-playback-relays.md) |

---

[← User Guide home](index.md)
