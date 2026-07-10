# Set Play

**Set Play** is the bandleader view for running a live set: track current/next songs, skip items, advance the show, and optionally broadcast state to band assistants.

Open from the **Set Play** page in the main nav.

---

## Loading a set {#load-set}

1. Choose a **Setlist** from the tree combo
2. Click **Load set**

Sets can load **without** a band layout; part-assignment UI is not used in that case.

---

## Song list checkboxes {#checkboxes}

Each song row has checkboxes:

| Flag | Meaning |
|------|---------|
| **Played** | Already performed this session |
| **Current** | The song being performed now |
| **Next** | Marked as up next |
| **Skip** | Excluded from automatic next-song selection |

---

## Advance song {#advance-song}

**Advance song** (large button):

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
