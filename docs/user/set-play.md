# Set Play

**Set Play** is the bandleader view for running a live set: track current/next songs, skip items, advance the show, and optionally broadcast state to band assistants.

Open from the **Set Play** page in the main nav.

---

## Loading a set {#load-set}

1. Choose a **Setlist** from the tree combo
2. Click **Load set**

Sets can load **without** a band layout; part-assignment UI is not used in that case.

---

## Song status {#status}

Each song has one primary **status** (shown as a badge) plus an optional **Skip** flag:

| Badge | Meaning |
|-------|---------|
| **NOW** | The song being performed now (at most one) |
| **NEXT** | Marked as up next (at most one) |
| **✓** | Already performed this session |
| **SKIP** | Excluded from automatic next-song selection |
| *(blank)* | Pending — not yet current, next, played, or skipped |

**Skip** is the only per-row checkbox. Change Current / Next / Played via the row **Actions** menu (button or right-click), or **double-click** a row to set it as Next:

| Action | Effect |
|--------|--------|
| **Double-click row** | Set as NEXT |
| **Set current** | Make this song NOW (clears Next/Skip/Played on that row) |
| **Set next** | Make this song NEXT (clears Current/Skip/Played on that row) |
| **Mark played** / **Clear played** | Toggle session played; Mark also logs to library play history. Clear only removes the session flag (library history is kept). |
| **Log at time…** | Log a library play at a chosen time |

Skipping a song that is Current or Next clears that pointer and rescans Next when needed.

---

## Advance song {#advance-song}

**Advance song** (large button) is the primary live control:

1. Current → Played
2. Next → Current
3. Next unskipped song in list → Next

Enable **Mark songs as played automatically** to write play history to the Library when advancing. Useful for live performances. Uncheck this when you are simply testing a set during private rehersal.

---

## Mark set as played

**Mark set as played (all non-skipped)…** logs play history for every non-skipped song in one step (with confirmation).

---

## Band layout panel {#band-grid}

When the loaded set has a band layout, the grid shows player positions.

**Part change highlighting** compares the **next** selected song to the **current** song (instrument/part changes between them).

The player name list below highlights selected members on the grid (local only — not broadcast). Useful to remind user of which player(s) they are controlling for visual reference.

---

## Broadcast (Cloudflare relay) {#broadcast}

Optional live sync for [Band Assistant](band-assistant.md) (app or browser):

1. Configure (or create) a relay in [Set Playback settings](settings/set-playback-relays.md) — **only the bandleader** needs this
2. Select that **Relay** on Set Play
3. Enable **Broadcast (Cloudflare relay)**
4. Share the **playback link** with assistants (**Copy link**). Example shape: `https://your-worker.workers.dev/playback?set=12AB3CD`

Assistants can open the link in a browser or paste it into Band Assistant — they do not need to configure the relay themselves.

Use **Reconnect** if the connection drops.

Set Play works locally without broadcast; relay is only needed for assistants.

**Note:** Existing relays must be **redeployed** once (Settings → Set Playback) so the worker serves the `/playback` page. WebSocket sync still works on older deploys; only the browser page requires the new assets.

---

[← User Guide home](index.md) · [Band Assistant](band-assistant.md) · [Setlists](setlists.md)
