/**
 * Band Assistant web client — connects to the same-origin Set Play relay.
 * Protocol: set_play_state_v1 (full snapshot over WebSocket).
 */
(function () {
  "use strict";

  const STATE_TYPE = "set_play_state_v1";
  const CARD_W = 9;
  const CARD_H = 7;
  const PPU = 15;
  const X_MIN = -145;
  const Y_MIN = -105;
  const EMPTY_PART = "---";

  const COLORS = {
    surface: "#12101a",
    outline: "#3d3654",
    onSurface: "#e8e4dc",
    textSecondary: "#b4a8a8",
    primary: "#c9a227",
    error: "#7a3030",
    warning: "#d48a3a",
    dup: "#ff4444",
  };

  const setInput = document.getElementById("set-input");
  const connectBtn = document.getElementById("connect-btn");
  const disconnectBtn = document.getElementById("disconnect-btn");
  const reconnectBtn = document.getElementById("reconnect-btn");
  const statusEl = document.getElementById("status");
  const statusPill = document.getElementById("status-pill");
  const setInfo = document.getElementById("set-info");
  const songTbody = document.getElementById("song-tbody");
  const playersList = document.getElementById("players-list");
  const connCode = document.getElementById("conn-code");
  const connHost = document.getElementById("conn-host");
  const connRev = document.getElementById("conn-rev");
  const currentTitle = document.getElementById("current-title");
  const currentMeta = document.getElementById("current-meta");
  const nextTitle = document.getElementById("next-title");
  const nextMeta = document.getElementById("next-meta");
  const layoutViewport = document.getElementById("layout-viewport");
  const canvas = document.getElementById("layout-canvas");
  const layoutEmpty = document.getElementById("layout-empty");
  const recenterBtn = document.getElementById("recenter-btn");
  const ctx = canvas.getContext("2d");

  const tabButtons = [...document.querySelectorAll(".tab")];
  const panels = {
    connection: document.getElementById("panel-connection"),
    setlist: document.getElementById("panel-setlist"),
    playback: document.getElementById("panel-playback"),
  };

  /** @type {WebSocket | null} */
  let ws = null;
  /** @type {string | null} */
  let lastCode = null;
  /** @type {Set<number>} */
  const highlightPlayers = new Set();
  /** @type {Array<object>} */
  let lastCards = [];
  /** @type {object | null} */
  let lastSnapshot = null;
  let hasSynced = false;
  /** @type {string} */
  let lastLayoutKey = "";
  let needsFit = false;

  // Canvas pan state (pixel offsets applied after logical→view transform)
  let viewOffsetX = 0;
  let viewOffsetY = 0;
  let panStart = null;

  function setStatus(msg) {
    statusEl.textContent = msg;
  }

  function setPill(text, kind) {
    statusPill.textContent = text;
    statusPill.classList.remove("ok", "warn");
    if (kind) statusPill.classList.add(kind);
  }

  function fmtDuration(sec) {
    if (sec == null || Number.isNaN(Number(sec))) return "—";
    const s = Math.max(0, Math.floor(Number(sec)));
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    const r = s % 60;
    if (h > 0) {
      return `${h}:${String(m).padStart(2, "0")}:${String(r).padStart(2, "0")}`;
    }
    return `${m}:${String(r).padStart(2, "0")}`;
  }

  function displayPartNumber(raw) {
    const s = raw == null ? "" : String(raw).trim();
    if (!s || s === "###" || s === "---") return EMPTY_PART;
    return s;
  }

  /**
   * @param {string} raw
   * @returns {{ code: string } | null}
   */
  function parseJoinInput(raw) {
    const text = (raw || "").trim();
    if (!text) return null;

    if (/^https?:\/\//i.test(text) || /^wss?:\/\//i.test(text)) {
      try {
        let urlStr = text;
        if (/^wss:\/\//i.test(urlStr)) urlStr = "https://" + urlStr.slice(6);
        else if (/^ws:\/\//i.test(urlStr)) urlStr = "http://" + urlStr.slice(5);
        const u = new URL(urlStr);
        const setParam = u.searchParams.get("set") || u.searchParams.get("code");
        if (setParam && setParam.trim().length >= 5) {
          return { code: setParam.trim().toUpperCase() };
        }
        const m = u.pathname.match(/\/api\/rooms\/([^/]+)/i);
        if (m && m[1].length >= 5) {
          return { code: decodeURIComponent(m[1]).toUpperCase() };
        }
      } catch {
        return null;
      }
      return null;
    }

    const code = text.toUpperCase().replace(/[^A-Z0-9]/g, "");
    if (code.length >= 5) return { code };
    return null;
  }

  function wsUrlForCode(code) {
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    return `${proto}//${location.host}/api/rooms/${encodeURIComponent(code)}/ws`;
  }

  function setContentTabsEnabled(on) {
    for (const btn of tabButtons) {
      if (btn.dataset.tab === "connection") continue;
      btn.disabled = !on;
    }
  }

  function showTab(name) {
    for (const btn of tabButtons) {
      const active = btn.dataset.tab === name;
      btn.classList.toggle("active", active);
      btn.setAttribute("aria-selected", active ? "true" : "false");
    }
    for (const [key, panel] of Object.entries(panels)) {
      const active = key === name;
      panel.classList.toggle("active", active);
      panel.hidden = !active;
    }
    if (name === "playback") {
      requestAnimationFrame(() => {
        resizeCanvas();
        if (needsFit || lastCards.length) {
          fitCardsToView();
        }
        drawGrid();
      });
    }
  }

  function disconnect() {
    if (ws) {
      try {
        ws.close();
      } catch {
        /* ignore */
      }
      ws = null;
    }
    disconnectBtn.disabled = true;
    reconnectBtn.disabled = !(lastCode && lastCode.length >= 5);
    setStatus("Disconnected.");
    setPill("Disconnected", "warn");
  }

  function connect(code) {
    const parsed = parseJoinInput(code) || (code ? { code: String(code).toUpperCase() } : null);
    if (!parsed || parsed.code.length < 5) {
      setStatus("Enter a valid set code or paste a share link.");
      setPill("Not connected");
      return;
    }
    lastCode = parsed.code;
    setInput.value = lastCode;
    connCode.textContent = lastCode;
    connHost.textContent = location.host;

    if (ws) {
      try {
        ws.onclose = null;
        ws.close();
      } catch {
        /* ignore */
      }
      ws = null;
    }

    setStatus("Connecting…");
    setPill("Connecting…", "warn");
    const url = wsUrlForCode(lastCode);
    ws = new WebSocket(url);

    ws.onopen = () => {
      disconnectBtn.disabled = false;
      reconnectBtn.disabled = false;
      setStatus("Connected — waiting for set state…");
      setPill("Connected", "ok");
    };

    ws.onclose = () => {
      ws = null;
      disconnectBtn.disabled = true;
      reconnectBtn.disabled = !!(lastCode && lastCode.length >= 5);
      setStatus("Relay disconnected.");
      setPill("Disconnected", "warn");
    };

    ws.onerror = () => {
      setStatus("Relay connection error.");
      setPill("Error", "warn");
    };

    ws.onmessage = (ev) => {
      let data;
      try {
        data = JSON.parse(String(ev.data));
      } catch {
        return;
      }
      if (!data || data.type !== STATE_TYPE) return;
      applySnapshot(data);
    };
  }

  function rowById(data, itemId) {
    if (itemId == null) return null;
    const rows = Array.isArray(data.rows) ? data.rows : [];
    return rows.find((r) => Number(r.item_id) === Number(itemId)) || null;
  }

  function songMetaLine(row) {
    if (!row) return "";
    const parts = [];
    if (row.part_count != null) parts.push(`${row.part_count} parts`);
    if (row.duration_seconds != null) parts.push(fmtDuration(row.duration_seconds));
    if (row.artist) parts.push(String(row.artist));
    return parts.join(" · ");
  }

  function applySnapshot(data) {
    lastSnapshot = data;
    const meta = data.set_meta || {};
    const lines = [
      `<b>${escapeHtml(meta.name || "Set")}</b>`,
      `Date: ${escapeHtml(meta.set_date || "—")}  Time: ${escapeHtml(meta.set_time || "—")}`,
      `Notes: ${escapeHtml((meta.notes || "").trim() || "—")}`,
    ];
    if (meta.computed_duration_seconds != null) {
      lines.push(`Duration (incl. switches): ${fmtDuration(meta.computed_duration_seconds)}`);
    }
    setInfo.innerHTML = lines.join("<br/>");

    const played = new Set((data.played_item_ids || []).map(Number));
    const skipped = new Set((data.skipped_item_ids || []).map(Number));
    const currentId = data.current_item_id != null ? Number(data.current_item_id) : null;
    const nextId = data.next_item_id != null ? Number(data.next_item_id) : null;
    const rows = Array.isArray(data.rows) ? data.rows : [];
    const order = Array.isArray(data.order_item_ids) ? data.order_item_ids.map(Number) : [];
    const byId = new Map(rows.map((r) => [Number(r.item_id), r]));
    const ordered = order.length
      ? order.map((id) => byId.get(id)).filter(Boolean)
      : rows;

    songTbody.replaceChildren();
    for (const r of ordered) {
      const id = Number(r.item_id);
      const tr = document.createElement("tr");
      if (skipped.has(id)) tr.className = "row-skipped";
      else if (currentId === id) tr.className = "row-current";
      else if (nextId === id) tr.className = "row-next";
      else if (played.has(id)) tr.className = "row-played";

      tr.innerHTML = [
        flagCell(played.has(id)),
        flagCell(currentId === id),
        flagCell(nextId === id),
        flagCell(skipped.has(id)),
        `<td>${escapeHtml(r.title || "")}</td>`,
        `<td>${escapeHtml(String(r.part_count ?? ""))}</td>`,
        `<td>${fmtDuration(r.duration_seconds)}</td>`,
        `<td>${escapeHtml(r.artist || "—")}</td>`,
      ].join("");
      songTbody.appendChild(tr);
    }

    const cur = rowById(data, currentId);
    const nxt = rowById(data, nextId);
    currentTitle.textContent = cur ? cur.title || "—" : "—";
    currentMeta.textContent = songMetaLine(cur);
    nextTitle.textContent = nxt ? nxt.title || "—" : "—";
    nextMeta.textContent = songMetaLine(nxt);

    lastCards = Array.isArray(data.next_layout_cards) ? data.next_layout_cards : [];
    const layoutKey = lastCards
      .map((c) => `${c.player_id}:${c.x},${c.y}`)
      .sort()
      .join("|");
    const layoutChanged = layoutKey !== lastLayoutKey;
    lastLayoutKey = layoutKey;

    renderPlayers(lastCards);
    recenterBtn.hidden = !lastCards.length;
    needsFit = needsFit || layoutChanged || !hasSynced;

    connRev.textContent = String(data.revision ?? "—");
    setStatus(`Synced (rev ${data.revision ?? "—"}).`);
    setPill(`Synced · rev ${data.revision ?? "—"}`, "ok");

    if (!hasSynced) {
      hasSynced = true;
      setContentTabsEnabled(true);
      showTab("playback");
    } else if (panels.playback.classList.contains("active")) {
      requestAnimationFrame(() => {
        resizeCanvas();
        if (needsFit) fitCardsToView();
        drawGrid();
      });
    }
  }

  function flagCell(on) {
    return `<td class="flag">${on ? "✓" : ""}</td>`;
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function renderPlayers(cards) {
    const names = new Map();
    for (const c of cards) {
      names.set(Number(c.player_id), String(c.player_name || `Player ${c.player_id}`));
    }
    playersList.replaceChildren();
    if (!names.size) {
      const empty = document.createElement("p");
      empty.className = "hint";
      empty.textContent = "No layout yet.";
      playersList.appendChild(empty);
      return;
    }
    const sorted = [...names.entries()].sort((a, b) => a[1].localeCompare(b[1]));
    for (const [pid, name] of sorted) {
      const label = document.createElement("label");
      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.checked = highlightPlayers.has(pid);
      cb.addEventListener("change", () => {
        if (cb.checked) highlightPlayers.add(pid);
        else highlightPlayers.delete(pid);
        drawGrid();
      });
      label.appendChild(cb);
      label.appendChild(document.createTextNode(name));
      playersList.appendChild(label);
    }
  }

  function logicalToView(lx, ly) {
    return [
      (lx - X_MIN) * PPU + viewOffsetX,
      (ly - Y_MIN) * PPU + viewOffsetY,
    ];
  }

  function viewToLogical(vx, vy) {
    return [
      (vx - viewOffsetX) / PPU + X_MIN,
      (vy - viewOffsetY) / PPU + Y_MIN,
    ];
  }

  function fitCardsToView() {
    const vw = layoutViewport.clientWidth;
    const vh = layoutViewport.clientHeight;
    if (!lastCards.length || vw < 8 || vh < 8) {
      // Pane not visible yet — retry when Playback tab is shown.
      needsFit = true;
      return;
    }

    let minX = Infinity;
    let minY = Infinity;
    let maxX = -Infinity;
    for (const c of lastCards) {
      const x = Number(c.x);
      const y = Number(c.y);
      minX = Math.min(minX, x);
      minY = Math.min(minY, y);
      maxX = Math.max(maxX, x + CARD_W);
    }

    // Horizontal: center the band bounding box in the pane.
    const centerX = (minX + maxX) / 2;
    viewOffsetX = vw / 2 - (centerX - X_MIN) * PPU;

    // Vertical: place the topmost card flush with the top of the pane
    // (small pad) so the full card is visible.
    const topPad = 8;
    viewOffsetY = topPad - (minY - Y_MIN) * PPU;
    needsFit = false;
  }

  function resizeCanvas() {
    const dpr = window.devicePixelRatio || 1;
    const w = layoutViewport.clientWidth || 1;
    const h = layoutViewport.clientHeight || 1;
    canvas.width = Math.floor(w * dpr);
    canvas.height = Math.floor(h * dpr);
    canvas.style.width = `${w}px`;
    canvas.style.height = `${h}px`;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }

  function cardsOverlap(a, b) {
    const ax = Number(a.x);
    const ay = Number(a.y);
    const bx = Number(b.x);
    const by = Number(b.y);
    return !(ax + CARD_W <= bx || bx + CARD_W <= ax || ay + CARD_H <= by || by + CARD_H <= ay);
  }

  function fitText(context, text, maxWidth, fontFamily, startPx, minPx) {
    let size = startPx;
    while (size >= minPx) {
      context.font = `${size}px ${fontFamily}`;
      if (context.measureText(text).width <= maxWidth) return size;
      size -= 1;
    }
    context.font = `${minPx}px ${fontFamily}`;
    return minPx;
  }

  function drawGrid() {
    if (!ctx) return;
    const w = layoutViewport.clientWidth || 1;
    const h = layoutViewport.clientHeight || 1;
    if (canvas.width === 0) resizeCanvas();

    ctx.clearRect(0, 0, w, h);
    ctx.fillStyle = COLORS.surface;
    ctx.fillRect(0, 0, w, h);

    if (!lastCards.length) {
      layoutEmpty.classList.remove("hidden");
      return;
    }
    layoutEmpty.classList.add("hidden");

    // Dotted graph paper (matches Qt paintEvent)
    const [lx0, ly0] = viewToLogical(0, 0);
    const [lx1, ly1] = viewToLogical(w, h);
    ctx.fillStyle = COLORS.outline;
    for (let lx = Math.floor(lx0); lx <= lx1 + 1; lx++) {
      for (let ly = Math.floor(ly0); ly <= ly1 + 1; ly++) {
        const [vx, vy] = logicalToView(lx, ly);
        if (vx >= 0 && vx < w && vy >= 0 && vy < h) {
          ctx.fillRect(Math.round(vx), Math.round(vy), 1, 1);
        }
      }
    }

    const fontFamily = getComputedStyle(document.body).fontFamily || "sans-serif";

    for (const card of lastCards) {
      const [vx, vy] = logicalToView(Number(card.x), Number(card.y));
      const cw = CARD_W * PPU;
      const ch = CARD_H * PPU;
      const overlap = lastCards.some((other) => other !== card && cardsOverlap(card, other));

      ctx.fillStyle = COLORS.surface;
      ctx.strokeStyle = overlap ? COLORS.error : COLORS.outline;
      ctx.lineWidth = overlap ? 2 : 1;
      roundRect(ctx, vx, vy, cw, ch, 4);
      ctx.fill();
      ctx.stroke();

      if (highlightPlayers.has(Number(card.player_id))) {
        ctx.strokeStyle = COLORS.primary;
        ctx.lineWidth = 2;
        roundRect(ctx, vx + 1, vy + 1, cw - 2, ch - 2, 4);
        ctx.stroke();
      }

      const margin = 2;
      const innerL = vx + margin;
      const innerT = vy + margin;
      const innerW = cw - margin * 2;
      const innerR = innerL + innerW;
      let y = innerT;

      const partDup = !!card.part_duplicate;
      const instChanged = !!card.instrument_changed_from_prior_in_set;
      const instWarn = !!card.instrument_warning;
      const useHeader = !!card.use_setlist_player_header;
      const partText = displayPartNumber(card.part_number);

      // Row 1: player name (+ gutters when setlist header)
      ctx.textBaseline = "middle";
      const nameSize = 12;
      ctx.font = `${nameSize}px ${fontFamily}`;
      const lineH = nameSize + 4;
      if (useHeader) {
        const gutter = ctx.measureText("999").width + 6;
        ctx.fillStyle = COLORS.textSecondary;
        ctx.textAlign = "left";
        ctx.fillText(String(card.neighbor_prev_part_label || ""), innerL, y + lineH / 2);
        ctx.textAlign = "right";
        ctx.fillText(String(card.neighbor_next_part_label || ""), innerR, y + lineH / 2);
        ctx.fillStyle = COLORS.onSurface;
        ctx.textAlign = "center";
        const name = String(card.player_name || "");
        fitText(ctx, name, Math.max(1, innerW - 2 * gutter), fontFamily, nameSize, 8);
        ctx.fillText(name, innerL + innerW / 2, y + lineH / 2, Math.max(1, innerW - 2 * gutter));
      } else {
        ctx.fillStyle = COLORS.onSurface;
        ctx.textAlign = "center";
        const name = String(card.player_name || "");
        fitText(ctx, name, innerW, fontFamily, nameSize, 8);
        ctx.fillText(name, innerL + innerW / 2, y + lineH / 2, innerW);
      }
      y += lineH + 2;

      // Row 2: large bold part number
      let partColor = COLORS.onSurface;
      if (partDup) partColor = COLORS.dup;
      else if (instChanged) partColor = COLORS.warning;
      ctx.fillStyle = partColor;
      ctx.textAlign = "center";
      const big = fitText(ctx, partText, innerW, fontFamily, 26, 12);
      ctx.font = `bold ${big}px ${fontFamily}`;
      const bigH = big + 4;
      ctx.fillText(partText, innerL + innerW / 2, y + bigH / 2, innerW);
      y += bigH + 2;

      // Row 3: instrument
      if (partDup) ctx.fillStyle = COLORS.dup;
      else if (instWarn) ctx.fillStyle = COLORS.warning;
      else ctx.fillStyle = COLORS.onSurface;
      const inst = String(card.instrument_name || "");
      fitText(ctx, inst, innerW, fontFamily, 11, 8);
      const instH = 14;
      ctx.fillText(inst, innerL + innerW / 2, y + instH / 2, innerW);
      y += instH + 2;

      // Row 4: part name
      ctx.fillStyle = partDup ? COLORS.dup : COLORS.onSurface;
      const pname = String(card.part_name || "");
      fitText(ctx, pname, innerW, fontFamily, 10, 7);
      ctx.fillText(pname, innerL + innerW / 2, y + 12 / 2, innerW);
    }
  }

  function roundRect(context, x, y, w, h, r) {
    const radius = Math.min(r, w / 2, h / 2);
    context.beginPath();
    context.moveTo(x + radius, y);
    context.arcTo(x + w, y, x + w, y + h, radius);
    context.arcTo(x + w, y + h, x, y + h, radius);
    context.arcTo(x, y + h, x, y, radius);
    context.arcTo(x, y, x + w, y, radius);
    context.closePath();
  }

  // Pan
  canvas.addEventListener("pointerdown", (e) => {
    canvas.setPointerCapture(e.pointerId);
    panStart = { x: e.clientX, y: e.clientY, ox: viewOffsetX, oy: viewOffsetY };
    canvas.classList.add("dragging");
  });
  canvas.addEventListener("pointermove", (e) => {
    if (!panStart) return;
    viewOffsetX = panStart.ox + (e.clientX - panStart.x);
    viewOffsetY = panStart.oy + (e.clientY - panStart.y);
    drawGrid();
  });
  function endPan() {
    panStart = null;
    canvas.classList.remove("dragging");
  }
  canvas.addEventListener("pointerup", endPan);
  canvas.addEventListener("pointercancel", endPan);

  window.addEventListener("resize", () => {
    if (!panels.playback.classList.contains("active")) return;
    resizeCanvas();
    if (needsFit) fitCardsToView();
    drawGrid();
  });

  recenterBtn.addEventListener("click", () => {
    fitCardsToView();
    drawGrid();
  });

  for (const btn of tabButtons) {
    btn.addEventListener("click", () => {
      if (btn.disabled) return;
      showTab(btn.dataset.tab);
    });
  }

  connectBtn.addEventListener("click", () => connect(setInput.value));
  disconnectBtn.addEventListener("click", () => disconnect());
  reconnectBtn.addEventListener("click", () => {
    if (lastCode) connect(lastCode);
    else connect(setInput.value);
  });
  setInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") connect(setInput.value);
  });

  connHost.textContent = location.host;

  // Auto-connect from ?set=
  const params = new URLSearchParams(location.search);
  const initial = params.get("set") || params.get("code");
  if (initial && initial.trim().length >= 5) {
    setInput.value = initial.trim().toUpperCase();
    connect(setInput.value);
  }
})();
