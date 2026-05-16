/**
 * Set Play relay: one Durable Object per room (SQLite-backed).
 * POST /api/rooms -> { roomCode, leaderToken }
 * WebSocket /api/rooms/:code/ws?leaderToken=... (leader) or without token (assistant)
 */

import { DurableObject } from "cloudflare:workers";

export interface Env {
  SET_PLAY_ROOM: DurableObjectNamespace<SetPlayRoom>;
}

function randomCode(): string {
  const alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
  let s = "";
  for (let i = 0; i < 7; i++) {
    s += alphabet[Math.floor(Math.random() * alphabet.length)];
  }
  return s;
}

function randomToken(): string {
  const bytes = new Uint8Array(24);
  crypto.getRandomValues(bytes);
  return [...bytes].map((b) => b.toString(16).padStart(2, "0")).join("");
}

export class SetPlayRoom extends DurableObject {
  private _initSchema(): void {
    this.ctx.storage.sql.exec(
      `CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT);`,
    );
  }

  private _getKv(key: string): string | null {
    let result: string | null = null;
    const cur = this.ctx.storage.sql.exec(
      "SELECT value FROM kv WHERE key = ?",
      key,
    );
    for (const row of cur) {
      result = String((row as { value?: string }).value ?? "");
    }
    return result;
  }

  private _setKv(key: string, value: string): void {
    this.ctx.storage.sql.exec(
      `INSERT INTO kv (key, value) VALUES (?, ?) 
       ON CONFLICT(key) DO UPDATE SET value = excluded.value`,
      key,
      value,
    );
  }

  async fetch(request: Request): Promise<Response> {
    this._initSchema();
    const url = new URL(request.url);

    if (url.pathname === "/internal/init" && request.method === "POST") {
      let body: { leaderToken?: string };
      try {
        body = (await request.json()) as { leaderToken?: string };
      } catch {
        return new Response("bad json", { status: 400 });
      }
      if (!body.leaderToken || body.leaderToken.length < 8) {
        return new Response("invalid token", { status: 400 });
      }
      this._setKv("leader_token", body.leaderToken);
      this._setKv("state_json", "{}");
      this._setKv("revision", "0");
      return new Response(JSON.stringify({ ok: true }), {
        headers: { "Content-Type": "application/json" },
      });
    }

    if (request.headers.get("Upgrade") !== "websocket") {
      return new Response("expected websocket", { status: 426 });
    }

    const leaderTokenParam =
      url.searchParams.get("leaderToken") ||
      url.searchParams.get("leader_token");
    const stored = this._getKv("leader_token");
    if (!stored) {
      return new Response("room not initialized", { status: 400 });
    }

    const isLeader = leaderTokenParam === stored;

    const webSocketPair = new WebSocketPair();
    const [client, server] = Object.values(webSocketPair);
    this.ctx.acceptWebSocket(server);

    server.serializeAttachment(JSON.stringify({ role: isLeader ? "leader" : "assistant" }));

    if (!isLeader) {
      const snap = this._getKv("state_json");
      if (snap && snap !== "{}" && snap.length > 2) {
        try {
          server.send(snap);
        } catch {
          /* ignore */
        }
      }
    }

    return new Response(null, { status: 101, webSocket: client });
  }

  async webSocketMessage(ws: WebSocket, message: string | ArrayBuffer): Promise<void> {
    const raw =
      typeof message === "string"
        ? message
        : new TextDecoder().decode(message);
    let att: { role: string };
    try {
      att = JSON.parse(ws.deserializeAttachment() as string) as { role: string };
    } catch {
      att = { role: "assistant" };
    }
    if (att.role !== "leader") {
      return;
    }

    let parsed: Record<string, unknown>;
    try {
      parsed = JSON.parse(raw) as Record<string, unknown>;
    } catch {
      return;
    }

    if (parsed.type !== "set_play_state_v1") {
      return;
    }

    const rev = Number(parsed.revision ?? 0);
    this._setKv("state_json", raw);
    this._setKv("revision", String(rev));

    for (const peer of this.ctx.getWebSockets()) {
      try {
        peer.send(raw);
      } catch {
        /* ignore */
      }
    }
  }

  async webSocketClose(
    _ws: WebSocket,
    _code: number,
    _reason: string,
    _wasClean: boolean,
  ): Promise<void> {
    /* hibernation */
  }
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === "/api/rooms" && request.method === "POST") {
      for (let attempt = 0; attempt < 16; attempt++) {
        const code = randomCode();
        const token = randomToken();
        const id = env.SET_PLAY_ROOM.idFromName(code);
        const stub = env.SET_PLAY_ROOM.get(id);
        const res = await stub.fetch(
          new Request("https://internal/internal/init", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ leaderToken: token }),
          }),
        );
        if (res.ok) {
          return Response.json({ roomCode: code, leaderToken: token });
        }
      }
      return new Response("could not allocate room", { status: 500 });
    }

    const m = url.pathname.match(/^\/api\/rooms\/([^/]+)\/ws$/);
    if (m) {
      const code = decodeURIComponent(m[1]).toUpperCase();
      const id = env.SET_PLAY_ROOM.idFromName(code);
      const stub = env.SET_PLAY_ROOM.get(id);
      return stub.fetch(request);
    }

    return new Response("Not found", { status: 404 });
  },
};
