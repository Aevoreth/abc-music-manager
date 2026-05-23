# Troubleshooting

Quick fixes for common issues. Each item links to detailed topics where available.

---

## Library is empty after install

1. Complete [First-time setup](getting-started.md#getting-started-checklist)
2. Run **File → Scan Library**
3. Click **Clear Filters** on the Library page ([filters](library.md#filters))

---

## Scan finds no songs

- Verify **Settings → Folder rules → LOTRO directory** points to the folder containing `Music\`
- Check that paths are not listed as excluded directories
- Confirm ABC files exist under Music

---

## Playback: no sound {#playback-no-sound}

- Open **Settings → ABC Playback** and set or browse for a soundfont
- Leave path empty to trigger default lookup / download
- Check system volume and that another app is not holding exclusive audio

See [Playback toolbar](playback.md) and [ABC Playback settings](settings/abc-playback.md).

---

## ABC file not found when playing

The database path may be stale if files moved. Re-scan the library. If duplicates were resolved, ensure the kept copy still exists on disk.

---

## PluginData write failed

- Confirm account targets are **enabled** ([Account targets](settings/account-targets.md))
- Verify LOTRO directory and PluginData paths
- Read the red lines in the **Write PluginData** log dialog

---

## Set Play relay won't connect {#relay-issues}

- Leader must enable **Broadcast** and share a valid room code
- Assistant must use the **same relay URL** as the leader
- URL format: `wss://…` or `https://…` with **no trailing slash**
- Deploy or verify your Cloudflare worker ([Set Playback relays](settings/set-playback-relays.md))

---

## Band Assistant can't join

- Confirm room code spelling
- Leader session must be active and broadcasting
- Try **Reconnect** on both sides

---

## Filters hiding all songs

Use **Clear Filters** (show everything) or **Reset Filters** (restore defaults from [Default filters](settings/default-filters.md)).

---

## Window off-screen / wrong monitor

**Settings → Appearance → Reset window geometry**

---

[← User Guide home](index.md)
