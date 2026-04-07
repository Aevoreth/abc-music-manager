"""
Band layout for setlist: clickable cards assign parts to players for the selected song.
Data saved to SetlistBandAssignment (setlist), not to the song.
"""

from __future__ import annotations

import json
import sqlite3
from collections import Counter

from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QMenu, QWidgetAction
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QEnterEvent

from ..services.app_state import AppState
from ..db.band_repo import list_layout_slots
from ..db.player_repo import list_players, list_player_instruments_bulk
from ..db.song_layout_repo import get_song_layout_assignments
from ..db.setlist_repo import (
    SetlistItemSongMetaRow,
    get_setlist_band_assignments,
    get_setlist_band_assignments_bulk,
    list_setlist_items_with_song_meta,
    upsert_setlist_band_assignment,
    delete_setlist_band_assignment,
)
from ..db.instrument import get_instrument_name, get_instrument_ids_with_same_name_ci
from .band_layout_grid import BandLayoutGridWidget, LayoutCard
from .theme import COLOR_TEXT_SECONDARY


def _as_instrument_id(raw: object) -> int | None:
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _instrument_id_for_part(parts_json: str | None, part_num: int) -> int | None:
    if not parts_json:
        return None
    try:
        raw = json.loads(parts_json)
    except json.JSONDecodeError:
        return None
    for p in raw:
        try:
            if int(p.get("part_number") or 0) == part_num:
                return _as_instrument_id(p.get("instrument_id"))
        except (TypeError, ValueError):
            continue
    return None


def _instruments_equivalent(conn: sqlite3.Connection, iid_a: int | None, iid_b: int | None) -> bool:
    if iid_a is None and iid_b is None:
        return True
    if iid_a is None or iid_b is None:
        return False
    if iid_a == iid_b:
        return True
    eq_a = get_instrument_ids_with_same_name_ci(conn, iid_a)
    return iid_b in eq_a


def _effective_part(
    overrides: dict[int, int | None],
    layout_assigns: dict[int, int | None],
    player_id: int,
) -> int | None:
    if player_id in overrides:
        return overrides[player_id]
    return layout_assigns.get(player_id)


class _HoverLabel(QLabel):
    """Label that highlights on hover for use in QMenu."""

    def __init__(self, text: str, base_style: str, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setMouseTracking(True)
        self._base_style = base_style
        self.setStyleSheet(base_style)

    def enterEvent(self, event: QEnterEvent) -> None:
        super().enterEvent(event)
        self.setStyleSheet(f"{self._base_style} background-color: #4a4260;")

    def leaveEvent(self, event) -> None:
        super().leaveEvent(event)
        self.setStyleSheet(self._base_style)


class SetlistBandAssignmentGrid(BandLayoutGridWidget):
    """Band grid in assignment mode: click card to show part menu. No drag."""

    partSelected = Signal(int, object)  # player_id, part_number|None

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        add_btn = self.get_add_player_button()
        add_btn.hide()
        add_btn.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._assignment_parts: list = []
        self._part_to_player: dict[int, int] = {}
        self._pan_x = 0.0
        self._pan_y = 0.0
        self._assignment_help_by_player: dict[int, str] = {}

    def set_assignment_help_by_player(self, help_by_player: dict[int, str]) -> None:
        self._assignment_help_by_player = dict(help_by_player)
        self.setToolTip("")

    def mouseMoveEvent(self, event) -> None:
        super().mouseMoveEvent(event)
        pos = event.position().toPoint()
        card = self._card_at(pos.x(), pos.y())
        if card:
            t = self._assignment_help_by_player.get(card.player_id, "")
            self.setToolTip(t)
        else:
            self.setToolTip("")

    def leaveEvent(self, event) -> None:
        super().leaveEvent(event)
        self.setToolTip("")

    def set_assignment_parts(self, parts: list) -> None:
        self._assignment_parts = list(parts)

    def set_part_assignments(self, part_to_player: dict[int, int]) -> None:
        """part_number -> player_id who has it. Used to show taken parts in red."""
        self._part_to_player = dict(part_to_player)

    def mousePressEvent(self, event) -> None:
        if event.button() in (Qt.MouseButton.LeftButton, Qt.MouseButton.RightButton):
            pos = event.position().toPoint()
            card = self._card_at(pos.x(), pos.y())
            if card:
                try:
                    current = None if card.part_number == "###" else int(card.part_number)
                except (ValueError, TypeError):
                    current = None
                self._show_part_menu(card.player_id, event.globalPos(), current_part=current)
                return
        super().mousePressEvent(event)

    def contextMenuEvent(self, event) -> None:
        card = self._card_at(event.pos().x(), event.pos().y())
        if card:
            try:
                current = None if card.part_number == "###" else int(card.part_number)
            except (ValueError, TypeError):
                current = None
            self._show_part_menu(card.player_id, event.globalPos(), current_part=current)
        else:
            super().contextMenuEvent(event)

    def _show_part_menu(self, player_id: int, global_pos, current_part: int | None = None) -> None:
        menu = QMenu(self)
        menu.setStyleSheet("QMenu::item { padding: 4px 12px; }")

        help_text = (self._assignment_help_by_player.get(player_id) or "").strip()
        if help_text:
            hl = QLabel(help_text)
            hl.setWordWrap(True)
            hl.setMaximumWidth(400)
            hl.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY}; padding: 6px 10px;")
            head = QWidgetAction(menu)
            head.setDefaultWidget(hl)
            menu.addAction(head)
            menu.addSeparator()

        base_none = "color: #4caf50;" if current_part is None else ""
        none_lbl = _HoverLabel("(None)", base_none)
        none_lbl.setMinimumWidth(220)
        none_act = QWidgetAction(menu)
        none_act.setDefaultWidget(none_lbl)
        none_act.setData(None)
        menu.addAction(none_act)

        texts = []
        for p in sorted(self._assignment_parts, key=lambda x: int(x.get("part_number") or 0)):
            pn = int(p["part_number"])
            pname = (p.get("part_name") or "").strip() or f"Part {pn}"
            iid = p.get("instrument_id")
            iname = get_instrument_name(self.app_state.conn, iid) if iid and hasattr(self, "app_state") else "—"
            texts.append((pn, f"#{pn} — {pname} — {iname}"))
        min_w = 220
        for pn, text in texts:
            other = self._part_to_player.get(pn)
            is_taken = other is not None and other != player_id
            is_current = pn == current_part
            base = "color: #4caf50;" if is_current else ("color: #ff4444;" if is_taken else "")
            lbl = _HoverLabel(text, base)
            lbl.setMinimumWidth(min_w)
            act = QWidgetAction(menu)
            act.setDefaultWidget(lbl)
            act.setData(pn)
            menu.addAction(act)
        action = menu.exec(global_pos)
        if action:
            self.partSelected.emit(player_id, action.data())


class SetlistBandAssignmentPanel(QWidget):
    """Band layout with clickable cards for part assignment (saved to setlist)."""

    assignment_changed = Signal()
    setlist_item_updated = Signal(int)  # setlist_item_id

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
        self._slots: list = []
        self._item_id: int | None = None
        self._layout_part_by_player: dict[int, int | None] = {}
        self._parts_list: list = []
        self._inst_bulk: dict[int, set[int]] = {}

    def clear(self) -> None:
        self._slots = []
        self.grid.set_cards([])
        self.grid.set_assignment_help_by_player({})
        self._item_id = None
        self._hint.setText("")
        self.grid.setVisible(False)

    def refresh(
        self,
        *,
        band_layout_id: int | None,
        setlist_item_id: int | None,
        song_layout_id: int | None,
        parts_json: str | None,
        setlist_id: int | None = None,
    ) -> None:
        self._slots = []
        self.grid.set_cards([])

        if not band_layout_id:
            self._hint.setText("Choose a band layout for this setlist to assign parts per song.")
            self.grid.setVisible(False)
            return

        if not setlist_item_id:
            self._hint.setText("Select a song in the set list.")
            self.grid.setVisible(False)
            return

        if not song_layout_id:
            self._hint.setText("Select a song in the set list. Song layout will be created when a band layout is set.")
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
        overrides = get_setlist_band_assignments(conn, setlist_item_id)
        pids = [s.player_id for s in slots]
        inst_bulk = list_player_instruments_bulk(conn, pids)

        self._hint.setText(
            "Click a card to assign a part for this song. Assignments are saved to the setlist."
        )
        self.grid.setVisible(True)
        self._item_id = setlist_item_id
        self._layout_part_by_player = dict(layout_assigns)
        self._parts_list = parts
        self._inst_bulk = inst_bulk
        self._slots = list(slots)
        self.grid.set_assignment_parts(parts)

        # Build part_number -> player_id for menu highlighting (parts taken by others)
        eff_assigns = {
            s.player_id: overrides.get(s.player_id) if s.player_id in overrides else layout_assigns.get(s.player_id)
            for s in slots
        }
        part_to_player = {pnum: pid for pid, pnum in eff_assigns.items() if pnum is not None}
        self.grid.set_part_assignments(part_to_player)

        part_counts = Counter(pnum for pnum in eff_assigns.values() if pnum is not None)
        duplicated_parts = {p for p, c in part_counts.items() if c > 1}

        setlist_rows: list[SetlistItemSongMetaRow] | None = None
        setlist_idx: int | None = None
        bulk_ov: dict[int, dict[int, int | None]] = {}
        layout_cache: dict[int | None, dict[int, int | None]] = {}

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

        if setlist_id is not None:
            setlist_rows = list_setlist_items_with_song_meta(conn, setlist_id)
            setlist_idx = next(
                (i for i, r in enumerate(setlist_rows) if r.item.id == setlist_item_id),
                None,
            )
            if setlist_idx is not None:
                item_ids = [r.item.id for r in setlist_rows]
                bulk_ov = get_setlist_band_assignments_bulk(conn, item_ids)

        help_by_player: dict[int, str] = {}

        cards = []
        for s in slots:
            eff = overrides[s.player_id] if s.player_id in overrides else layout_assigns.get(s.player_id)
            part_dup = eff is not None and eff in duplicated_parts
            if eff is not None and eff in parts_by_num:
                meta = parts_by_num[eff]
                pn = str(meta.get("part_number", eff))
                pname = (meta.get("part_name") or "").strip() or f"Part {eff}"
                iid = _as_instrument_id(meta.get("instrument_id"))
                iname = get_instrument_name(conn, iid) if iid else "—"
                # Match by ID or by same name (case-insensitive) for ABC duplicates
                equiv_ids = get_instrument_ids_with_same_name_ci(conn, iid) if iid else frozenset()
                has_inst = bool(equiv_ids and (inst_bulk.get(s.player_id, set()) & equiv_ids))
                inst_warn = bool(iid and not has_inst)
            else:
                pn = "###"
                pname = "(Part Name)"
                iname = "(Made for Instrument)"
                inst_warn = False
                iid = None

            use_header = bool(setlist_rows is not None and setlist_idx is not None)
            prev_l = ""
            next_l = ""
            inst_changed = False
            if use_header:
                assert setlist_rows is not None and setlist_idx is not None
                row_before = setlist_rows[setlist_idx - 1] if setlist_idx > 0 else None
                row_after = (
                    setlist_rows[setlist_idx + 1] if setlist_idx + 1 < len(setlist_rows) else None
                )
                if row_before is not None:
                    ppn = eff_for_row(row_before, s.player_id)
                    if ppn is not None:
                        prev_l = str(ppn)
                if row_after is not None:
                    npn = eff_for_row(row_after, s.player_id)
                    if npn is not None:
                        next_l = str(npn)

                prior_iid: int | None = None
                prior_title = ""
                prior_pn: int | None = None
                for j in range(setlist_idx - 1, -1, -1):
                    back = setlist_rows[j]
                    bpn = eff_for_row(back, s.player_id)
                    if bpn is not None:
                        prior_iid = _instrument_id_for_part(back.parts_json, bpn)
                        prior_title = back.title
                        prior_pn = bpn
                        break

                if (
                    not part_dup
                    and eff is not None
                    and eff in parts_by_num
                    and iid is not None
                    and prior_iid is not None
                ):
                    inst_changed = not _instruments_equivalent(conn, iid, prior_iid)

                lines: list[str] = []
                if prior_pn is not None and prior_title:
                    piname = (
                        get_instrument_name(conn, prior_iid) if prior_iid is not None else "—"
                    )
                    lines.append(
                        f"Last assignment in this set: \"{prior_title}\" — Part {prior_pn} — {piname}"
                    )
                else:
                    lines.append("No earlier assignment in this set for this player.")
                if setlist_idx > 0:
                    lines.append(f"Previous song in set: {prev_l or '—'}")
                if setlist_idx + 1 < len(setlist_rows):
                    lines.append(f"Next song in set: {next_l or '—'}")
                help_by_player[s.player_id] = "\n".join(lines)

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
                    use_setlist_player_header=use_header,
                    neighbor_prev_part_label=prev_l,
                    neighbor_next_part_label=next_l,
                    instrument_changed_from_prior_in_set=inst_changed,
                )
            )
        self.grid.set_assignment_help_by_player(help_by_player)
        self.grid.set_cards(cards)

    def _on_part_selected(self, player_id: int, part_number: int | None) -> None:
        if self._item_id is None:
            return
        conn = self.app_state.conn
        bl = self._layout_part_by_player.get(player_id)
        if part_number == bl:
            delete_setlist_band_assignment(conn, self._item_id, player_id)
        else:
            upsert_setlist_band_assignment(conn, self._item_id, player_id, part_number)
        self.assignment_changed.emit()
        if self._item_id is not None:
            self.setlist_item_updated.emit(self._item_id)
