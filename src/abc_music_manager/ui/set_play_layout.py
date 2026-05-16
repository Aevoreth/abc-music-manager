"""Build read-only LayoutCard list for Set Play (up-next song, gutters from current / after-next)."""

from __future__ import annotations

import json
from collections import Counter

import sqlite3

from ..db.band_repo import list_layout_slots
from ..db.player_repo import list_players, list_player_instruments_bulk
from ..db.song_layout_repo import get_song_layout_assignments
from ..db.setlist_repo import (
    SetlistItemSongMetaRow,
    get_setlist_band_assignments,
    get_setlist_band_assignments_bulk,
)
from ..db.instrument import get_instrument_name, get_instrument_ids_with_same_name_ci
from .band_layout_grid import LayoutCard
from .setlist_band_assignment_panel import (
    _effective_part,
    _instrument_id_for_part,
    _instruments_equivalent,
)


def _as_instrument_id(raw: object) -> int | None:
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _eff_for_item(
    conn: sqlite3.Connection,
    row: SetlistItemSongMetaRow | None,
    player_id: int,
) -> int | None:
    if row is None or not row.item.song_layout_id:
        return None
    layout_assigns = {
        a.player_id: a.part_number
        for a in get_song_layout_assignments(conn, row.item.song_layout_id)
    }
    overrides = get_setlist_band_assignments(conn, row.item.id)
    return _effective_part(overrides, layout_assigns, player_id)


def build_set_play_layout_cards(
    conn: sqlite3.Connection,
    *,
    band_layout_id: int,
    next_row: SetlistItemSongMetaRow | None,
    current_row: SetlistItemSongMetaRow | None,
    right_row: SetlistItemSongMetaRow | None,
    setlist_rows: list[SetlistItemSongMetaRow] | None = None,
) -> list[LayoutCard]:
    """Cards show **next** row assignments; gutters: current (left), row after next (right).

    When ``setlist_rows`` is provided (full set order), part numbers use the same gold
    highlight as the setlist editor when the instrument differs from the latest earlier
    assignment for that player in the set.
    """
    if next_row is None or not next_row.item.song_layout_id:
        return []

    slots = list_layout_slots(conn, band_layout_id)
    if not slots:
        return []

    players = {p.id: p.name for p in list_players(conn)}
    parts = json.loads(next_row.parts_json) if next_row.parts_json else []
    parts_by_num = {int(p["part_number"]): p for p in parts}
    layout_assigns = {
        a.player_id: a.part_number
        for a in get_song_layout_assignments(conn, next_row.item.song_layout_id)
    }
    overrides = get_setlist_band_assignments(conn, next_row.item.id)
    pids = [s.player_id for s in slots]
    inst_bulk = list_player_instruments_bulk(conn, pids)

    eff_assigns = {
        s.player_id: overrides.get(s.player_id) if s.player_id in overrides else layout_assigns.get(s.player_id)
        for s in slots
    }
    part_counts = Counter(pnum for pnum in eff_assigns.values() if pnum is not None)
    duplicated_parts = {p for p, c in part_counts.items() if c > 1}

    setlist_idx: int | None = None
    bulk_ov: dict[int, dict[int, int | None]] = {}
    layout_cache: dict[int | None, dict[int, int | None]] = {}

    if setlist_rows and next_row is not None:
        setlist_idx = next(
            (i for i, r in enumerate(setlist_rows) if r.item.id == next_row.item.id),
            None,
        )
        if setlist_idx is not None:
            item_ids = [r.item.id for r in setlist_rows]
            bulk_ov = get_setlist_band_assignments_bulk(conn, item_ids)

    def layout_for(slayout_id: int | None) -> dict[int, int | None]:
        if slayout_id not in layout_cache:
            if not slayout_id:
                layout_cache[slayout_id] = {}
            else:
                layout_cache[slayout_id] = {
                    a.player_id: a.part_number
                    for a in get_song_layout_assignments(conn, slayout_id)
                }
        return layout_cache[slayout_id]

    def eff_for_row(row: SetlistItemSongMetaRow, pid: int) -> int | None:
        ov = bulk_ov.get(row.item.id, {})
        la = layout_for(row.item.song_layout_id)
        return _effective_part(ov, la, pid)

    cards: list[LayoutCard] = []
    for s in slots:
        eff = overrides.get(s.player_id) if s.player_id in overrides else layout_assigns.get(s.player_id)
        part_dup = eff is not None and eff in duplicated_parts
        iid: int | None = None
        if eff is not None and eff in parts_by_num:
            meta = parts_by_num[eff]
            pn = str(meta.get("part_number", eff))
            pname = (meta.get("part_name") or "").strip() or f"Part {eff}"
            iid = _as_instrument_id(meta.get("instrument_id"))
            iname = get_instrument_name(conn, iid) if iid else "—"
            equiv_ids = get_instrument_ids_with_same_name_ci(conn, iid) if iid else frozenset()
            has_inst = bool(equiv_ids and (inst_bulk.get(s.player_id, set()) & equiv_ids))
            inst_warn = bool(iid and not has_inst)
        else:
            pn = "###"
            pname = "(Part Name)"
            iname = "(Made for Instrument)"
            inst_warn = False

        inst_changed = False
        if (
            setlist_rows is not None
            and setlist_idx is not None
            and setlist_idx > 0
        ):
            prior_iid: int | None = None
            for j in range(setlist_idx - 1, -1, -1):
                back = setlist_rows[j]
                bpn = eff_for_row(back, s.player_id)
                if bpn is not None:
                    prior_iid = _instrument_id_for_part(back.parts_json, bpn)
                    break
            if (
                not part_dup
                and eff is not None
                and eff in parts_by_num
                and iid is not None
                and prior_iid is not None
            ):
                inst_changed = not _instruments_equivalent(conn, iid, prior_iid)

        cur_pn = _eff_for_item(conn, current_row, s.player_id)
        right_pn = _eff_for_item(conn, right_row, s.player_id)
        prev_l = str(cur_pn) if cur_pn is not None else ""
        next_l = str(right_pn) if right_pn is not None else ""

        cards.append(
            LayoutCard(
                player_id=s.player_id,
                player_name=players.get(s.player_id, str(s.player_id)),
                x=s.x,
                y=s.y,
                part_number=pn,
                part_name=pname,
                instrument_name=iname,
                instrument_warning=inst_warn,
                part_duplicate=part_dup,
                use_setlist_player_header=True,
                neighbor_prev_part_label=prev_l,
                neighbor_next_part_label=next_l,
                instrument_changed_from_prior_in_set=inst_changed,
            )
        )
    return cards


def layout_cards_to_payload(cards: list[LayoutCard]) -> list[dict]:
    return [
        {
            "player_id": c.player_id,
            "player_name": c.player_name,
            "x": c.x,
            "y": c.y,
            "part_number": c.part_number,
            "part_name": c.part_name,
            "instrument_name": c.instrument_name,
            "instrument_warning": c.instrument_warning,
            "part_duplicate": c.part_duplicate,
            "use_setlist_player_header": c.use_setlist_player_header,
            "neighbor_prev_part_label": c.neighbor_prev_part_label,
            "neighbor_next_part_label": c.neighbor_next_part_label,
            "instrument_changed_from_prior_in_set": c.instrument_changed_from_prior_in_set,
        }
        for c in cards
    ]


def layout_cards_from_payload(data: list[dict]) -> list[LayoutCard]:
    out: list[LayoutCard] = []
    for d in data:
        out.append(
            LayoutCard(
                player_id=int(d["player_id"]),
                player_name=str(d["player_name"]),
                x=int(d["x"]),
                y=int(d["y"]),
                part_number=str(d.get("part_number", "###")),
                part_name=str(d.get("part_name", "")),
                instrument_name=str(d.get("instrument_name", "")),
                instrument_warning=bool(d.get("instrument_warning", False)),
                part_duplicate=bool(d.get("part_duplicate", False)),
                use_setlist_player_header=bool(d.get("use_setlist_player_header", False)),
                neighbor_prev_part_label=str(d.get("neighbor_prev_part_label", "")),
                neighbor_next_part_label=str(d.get("neighbor_next_part_label", "")),
                instrument_changed_from_prior_in_set=bool(
                    d.get("instrument_changed_from_prior_in_set", False)
                ),
            )
        )
    return out
