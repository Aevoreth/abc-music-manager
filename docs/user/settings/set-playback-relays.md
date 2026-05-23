# Settings — Set Playback relays

**Settings → Set Playback**

Named Cloudflare relay URLs for [Set Play](../set-play.md) and [Band Assistant](../band-assistant.md).

---

## Why relays?

Broadcasting Set Play state to assistants uses a small **Cloudflare Worker** WebSocket relay. Each bandleader can deploy their own worker (free tier is typically sufficient for band use).

---

## Add a relay

1. Click **Add relay**
2. Enter a **Name** (e.g. "Main band") and **URL** (`wss://your-worker.workers.dev` or `https://…`, **no trailing slash**)

Select the active relay from the combo box on Set Play and Band Assistant pages.

---

## Deploy helper {#deploy-relay}

**Create your own relay (deploy helper)…** opens an in-app wizard that bundles the worker template from the app and walks through Wrangler deploy steps.

You need:

- A Cloudflare account (free)
- Node.js / npm for `wrangler deploy` (wizard instructions)

*(Add step-by-step screenshots here later.)*

---

## End-to-end workflow

1. Deploy a worker and add its URL here
2. On **Set Play**: select relay → **Load set** → enable **Broadcast** → **Copy code**
3. On **Band Assistant**: same relay → enter code → **Connect**

See [Set Play → Broadcast](../set-play.md#broadcast) and [Troubleshooting → Relay](../troubleshooting.md#relay-issues).

---

[← User Guide home](../index.md) · [Set Play](../set-play.md) · [Band Assistant](../band-assistant.md)
