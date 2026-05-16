"""JSON snapshot for Set Play relay (DECISIONS §015 Phase 2)."""

from __future__ import annotations

from typing import Any

from ..services.set_play_state import SetPlaySessionState
from ..db.setlist_repo import SetlistRow, SetlistItemSongMetaRow
from ..ui.set_play_layout import layout_cards_to_payload
from ..ui.band_layout_grid import LayoutCard


STATE_TYPE = "set_play_state_v1"


def snapshot_from_leader(
    state: SetPlaySessionState,
    setlist: SetlistRow,
    song_rows: list[SetlistItemSongMetaRow],
    *,
    computed_duration_seconds: int | None,
    layout_cards: list[LayoutCard],
) -> dict[str, Any]:
    by_item = {r.item.id: r for r in song_rows}
    row_payloads = []
    for iid in state.order_item_ids:
        r = by_item.get(iid)
        if not r:
            continue
        row_payloads.append(
            {
                "item_id": r.item.id,
                "song_id": r.item.song_id,
                "position": r.item.position,
                "title": r.title,
                "part_count": r.part_count,
                "duration_seconds": r.duration_seconds,
                "artist": r.composers or "—",
            }
        )
    return {
        "type": STATE_TYPE,
        "revision": state.revision,
        "setlist_id": setlist.id,
        "set_meta": {
            "name": setlist.name,
            "notes": setlist.notes,
            "set_date": setlist.set_date,
            "set_time": setlist.set_time,
            "target_duration_seconds": setlist.target_duration_seconds,
            "default_change_duration_seconds": setlist.default_change_duration_seconds,
            "computed_duration_seconds": computed_duration_seconds,
            "band_layout_id": setlist.band_layout_id,
        },
        "order_item_ids": list(state.order_item_ids),
        "rows": row_payloads,
        "played_item_ids": sorted(state.played_item_ids),
        "current_item_id": state.current_item_id,
        "next_item_id": state.next_item_id,
        "skipped_item_ids": sorted(state.skipped_item_ids),
        "next_layout_cards": layout_cards_to_payload(layout_cards),
    }


def apply_snapshot_to_session(
    data: dict[str, Any],
) -> tuple[SetPlaySessionState, dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    """Parse leader JSON into session + set_meta + rows (for assistant UI)."""
    meta = data.get("set_meta") or {}
    st = SetPlaySessionState(
        order_item_ids=[int(x) for x in data.get("order_item_ids") or []],
        played_item_ids=set(int(x) for x in data.get("played_item_ids") or []),
        current_item_id=data.get("current_item_id"),
        next_item_id=data.get("next_item_id"),
        skipped_item_ids=set(int(x) for x in data.get("skipped_item_ids") or []),
        revision=int(data.get("revision") or 0),
    )
    if st.current_item_id is not None:
        st.current_item_id = int(st.current_item_id)
    if st.next_item_id is not None:
        st.next_item_id = int(st.next_item_id)
    rows = list(data.get("rows") or [])
    cards = list(data.get("next_layout_cards") or [])
    return st, meta, rows, cards
