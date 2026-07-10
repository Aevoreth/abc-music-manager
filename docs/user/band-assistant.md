# Band Assistant

**Band Assistant** lets band members follow a bandleader's Set Play session. You can use the in-app page, or open the bandleader’s share link in any browser — no app install and no relay configuration required for assistants.

---

## In-app vs standalone {#standalone-mode}

- **In app:** open **Band Assistant** from the left nav
- **Browser:** open the share link the bandleader copies from Set Play (`https://…/playback?set=CODE`). The page is served by the bandleader’s Cloudflare relay after they deploy/redeploy the worker that ships with the app.
- **Standalone app window:** `python main.py --assistant` (developers) or the Band Assistant entry if packaged

---

## Connecting {#connect}

1. Leader enables **Broadcast** on [Set Play](set-play.md#broadcast) and shares the **playback link** (**Copy link**)
2. **Either:**
   - Open the link in a browser, or
   - On **Band Assistant**, paste the full link into **Share link or code** and click **Connect**
3. The app (or browser page) reads the relay host and set code from the link — you do **not** need to add the relay in Settings

**Bare room code (legacy):** you can still paste only the code if you select the same **Relay (for bare code)** as the leader (configured under [Set Playback settings](settings/set-playback-relays.md)).

Use **Reconnect** after connection drops. **Disconnect** leaves the session.

If the browser shows **404** on `/playback`, the leader’s worker was deployed before the playback page existed — ask them to **redeploy** from Settings → Set Playback.

---

## What syncs {#what-syncs}

Assistants receive the leader's Set Play state:

- Current / next / skip / played flags
- Loaded setlist identity
- Band layout grid and part-change highlighting

---

## What does not sync

Selecting player names to highlight on the grid is **local to each client** (leader, assistant app, or browser) and is not broadcast. Useful to remind you which player(s) you are controlling for visual reference.

---

[← User Guide home](index.md) · [Set Play](set-play.md) · [Set Playback relays](settings/set-playback-relays.md)
