"""
Song layout assignment panel: clickable cards assign parts to players for a song.
Data saved to SongLayoutAssignment (song's layout per band). Setlists copy this but are independent.
"""

from __future__ import annotations

import json
from collections import Counter

from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PySide6.QtCore import Signal

from ..services.app_state import AppState
from ..db.band_repo import list_layout_slots
from ..db.player_repo import list_players, list_player_instruments_bulk
from ..db.song_layout_repo import get_song_layout_assignments, set_song_layout_assignment
from ..db.instrument import get_instrument_name, get_instrument_ids_with_same_name_ci
from .setlist_band_assignment_panel import SetlistBandAssignmentGrid
from .band_layout_grid import LayoutCard


class SongLayoutAssignmentPanel(QWidget):
    """Band layout with clickable cards for part assignment (saved to song layout)."""

    assignment_changed = Signal()

    def __init__(self, app_state: AppState, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.app_state = app_state
        v = QVBoxLayout(self)
        self._hint = QLabel()
        self._hint.setWordWrap(True)
        v.addWidget(self._hint)
        self.grid = SetlistBandAssignmentGrid(self)
        self.grid.app_state = app_state
        self.grid.partSelected.connect(self._on_part_selected)
        v.addWidget(self.grid, 1)
        self._song_layout_id: int | None = None
        self._refresh_params: dict = {}

    def clear(self) -> None:
        self.grid.set_cards([])
        self._song_layout_id = None
        self._hint.setText("")
        self.grid.setVisible(False)

    def refresh(
        self,
        *,
        band_layout_id: int | None,
        song_layout_id: int | None,
        parts_json: str | None,
    ) -> None:
        self.grid.set_cards([])

        if not band_layout_id:
            self._hint.setText("Select a band layout.")
            self.grid.setVisible(False)
            return

        if not song_layout_id:
            self._hint.setText("No song layout for this band yet. Save to create.")
            self.grid.setVisible(False)
            return

        conn = self.app_state.conn
        slots = list_layout_slots(conn, band_layout_id)
        if not slots:
            self._hint.setText("The selected band layout has no players on the grid.")
            self.grid.setVisible(False)
            return

        players = {p.id: p.name for p in list_players(conn)}
        parts = json.loads(parts_json) if parts_json else []
        parts_by_num = {int(p["part_number"]): p for p in parts}
        layout_assigns: dict[int, int | None] = {}
        for a in get_song_layout_assignments(conn, song_layout_id):
            layout_assigns[a.player_id] = a.part_number

        self._hint.setText(
            "Click a card to assign a part for this song. Saved to the song's layout (setlists copy this but are independent)."
        )
        self.grid.setVisible(True)
        self._song_layout_id = song_layout_id
        self._refresh_params = {
            "band_layout_id": band_layout_id,
            "song_layout_id": song_layout_id,
            "parts_json": parts_json,
        }
        self.grid.set_assignment_parts(parts)

        part_to_player = {pnum: pid for pid, pnum in layout_assigns.items() if pnum is not None}
        self.grid.set_part_assignments(part_to_player)

        part_counts = Counter(pnum for pnum in layout_assigns.values() if pnum is not None)
        duplicated_parts = {p for p, c in part_counts.items() if c > 1}
        pids = [s.player_id for s in slots]
        inst_bulk = list_player_instruments_bulk(conn, pids)

        cards = []
        for s in slots:
            eff = layout_assigns.get(s.player_id)
            part_dup = eff is not None and eff in duplicated_parts
            if eff is not None and eff in parts_by_num:
                meta = parts_by_num[eff]
                pn = str(meta.get("part_number", eff))
                pname = (meta.get("part_name") or "").strip() or f"Part {eff}"
                iid = meta.get("instrument_id")
                iname = get_instrument_name(conn, iid) if iid else "—"
                equiv_ids = get_instrument_ids_with_same_name_ci(conn, iid) if iid else frozenset()
                has_inst = bool(equiv_ids and (inst_bulk.get(s.player_id, set()) & equiv_ids))
                inst_warn = bool(iid and not has_inst)
            else:
                pn = "###"
                pname = "(Part Name)"
                iname = "(Made for Instrument)"
                inst_warn = False

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
                )
            )
        self.grid.set_cards(cards)

    def _on_part_selected(self, player_id: int, part_number: int | None) -> None:
        if self._song_layout_id is None:
            return
        set_song_layout_assignment(self.app_state.conn, self._song_layout_id, player_id, part_number)
        self.refresh(**self._refresh_params)
        self.assignment_changed.emit()
