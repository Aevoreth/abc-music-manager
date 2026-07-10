# Settings — Set Playback relays

**Settings → Set Playback**

Named Cloudflare relay URLs for [Set Play](../set-play.md) broadcast. **Only the bandleader** needs a relay configured here. Band assistants join via the share link (browser or paste into [Band Assistant](../band-assistant.md)) and do not need this settings page.

---

## Why relays?

Broadcasting Set Play state to assistants uses a small **Cloudflare Worker** WebSocket relay (plus a `/playback` Band Assistant page on the same worker). Each bandleader can deploy their own worker (free tier is more than sufficient for even heavy band usage).

---

## Add a relay

1. Click **Add relay**
2. Enter a **Name** (e.g. "Main band") and **URL** (`wss://your-worker.workers.dev` or `https://…`, **no trailing slash**)

Select the active relay from the combo box on the **Set Play** page when broadcasting.

---

## Deploy helper {#deploy-relay}

**Create your own relay (deploy helper)…** opens an in-app wizard that bundles the worker template from the app and walks through Wrangler deploy steps.

You need:

- A Cloudflare account (free)
- Node.js / npm for `wrangler deploy` (wizard provides instructions and in most cases can handle semi-automatic installation of these items)

If you already deployed a relay before the `/playback` page existed, use **Redeploy worker on Cloudflare…** so assistants can open the share link in a browser.

---

## End-to-end workflow

1. Deploy a worker and add its URL here (bandleader only)
2. On **Set Play**: select relay → **Load set** → enable **Broadcast** → **Copy link**
3. Assistants: open the link in a browser, or paste it into **Band Assistant** → **Connect**

See [Set Play → Broadcast](../set-play.md#broadcast) and [Troubleshooting → Relay](../troubleshooting.md#relay-issues).

---

[← User Guide home](../index.md) · [Set Play](../set-play.md) · [Band Assistant](../band-assistant.md)
