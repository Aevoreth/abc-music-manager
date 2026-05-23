"""
Set Play: bandleader and assistant UIs, band grid (up-next + gutters), relay sync.
"""

from __future__ import annotations

import json
import urllib.error
from typing import Any

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDateTimeEdit,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..services.app_state import AppState
from ..services.playback_state import PlaybackState
from ..services.preferences import (
    get_active_set_play_relay_url,
    get_set_play_relays,
    get_set_play_selected_relay_id,
    set_set_play_selected_relay_id,
)
from ..services.set_play_state import (
    SetPlaySessionState,
    advance_song,
    apply_exclusive_current,
    apply_exclusive_next,
    scan_next_item_id,
    toggle_skip,
)
from ..services.set_play_sync import STATE_TYPE, apply_snapshot_to_session, snapshot_from_leader
from ..services.set_play_relay_client import SetPlayRelayClient
from ..services.set_play_relay_http import create_relay_room
from ..db.setlist_repo import (
    SetlistItemRow,
    SetlistItemSongMetaRow,
    SetlistRow,
    list_setlists,
    list_setlist_items_with_song_meta,
)
from .setlist_picker_combo import SetlistPickerCombo
from ..db.play_log import log_play, log_play_at
from .band_layout_grid import BandLayoutGridWidget, LayoutCard
from .set_play_layout import (
    build_set_play_layout_cards,
    layout_cards_from_payload,
)
from .theme import (
    COLOR_ERROR,
    COLOR_ON_SURFACE,
    COLOR_OUTLINE,
    COLOR_OUTLINE_VARIANT,
    COLOR_PRIMARY,
    COLOR_SURFACE,
    COLOR_SURFACE_VARIANT,
    COLOR_TEXT_DISABLED,
    COLOR_TEXT_SECONDARY,
)


def _fmt_duration(sec: int | None) -> str:
    if sec is None:
        return "—"
    m, s = divmod(int(sec), 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def _fmt_hhmmss(sec: int) -> str:
    sec = max(0, int(sec))
    h, m = divmod(sec, 3600)
    m, s = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}"


class SetPlayReadOnlyBandGrid(BandLayoutGridWidget):
    """Pan only; no card drag or context menu."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.get_add_player_button().hide()

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        self._pan_start = event.position().toPoint()

    def mouseMoveEvent(self, event) -> None:
        if self._pan_start is not None:
            pos = event.position().toPoint()
            dx = pos.x() - self._pan_start.x()
            dy = pos.y() - self._pan_start.y()
            self._pan_x -= dx / self._pixels_per_unit
            self._pan_y -= dy / self._pixels_per_unit
            self._pan_start = pos
            self.update()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        self._pan_start = None

    def contextMenuEvent(self, event) -> None:
        pass


class SetPlayView(QWidget):
    """
    Bandleader (`assistant_mode=False`) or Band Assistant (`assistant_mode=True`).
    """

    COL_PLAYED = 0
    COL_CURRENT = 1
    COL_NEXT = 2
    COL_SKIP = 3
    COL_TITLE = 4
    COL_PARTS = 5
    COL_DUR = 6
    COL_ARTIST = 7
    COL_ACTIONS = 8

    def __init__(
        self,
        app_state: AppState | None,
        playback_state: PlaybackState | None = None,
        *,
        assistant_mode: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.app_state = app_state
        self.playback_state = playback_state
        self._assistant_mode = assistant_mode
        self._session = SetPlaySessionState(order_item_ids=[])
        self._song_rows: list[SetlistItemSongMetaRow] = []
        self._setlist: SetlistRow | None = None
        self._checkbox_guard = False
        self._layout_cards: list[LayoutCard] = []
        self._relay = SetPlayRelayClient(self)
        self._relay_code: str | None = None
        self._relay_leader_token: str | None = None
        self._last_pushed_revision: int = -1
        self._leader_reconnect_btn: QPushButton | None = None

        self._relay.connected_ok.connect(self._on_relay_connected)
        self._relay.disconnected.connect(self._on_relay_disconnected)
        self._relay.state_received.connect(self._on_relay_state)
        self._relay.error_occurred.connect(self._on_relay_error)

        self._highlight_players: set[int] = set()

        root = QVBoxLayout(self)
        root.setSpacing(6)

        self._table = QTableWidget()
        self._table.setColumnCount(9)
        self._table.setHorizontalHeaderLabels(
            ["Played", "Cur", "Next", "Skip", "Title", "Parts", "Duration", "Artist", "Actions"]
        )
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        hh = self._table.horizontalHeader()
        for c in range(9):
            hh.setSectionResizeMode(c, hh.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(self.COL_TITLE, hh.ResizeMode.Stretch)

        self._players_inner = QWidget()
        self._players_inner_layout = QVBoxLayout(self._players_inner)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self._players_inner)
        scroll.setMinimumWidth(160)
        self._players_group = QGroupBox("Your players")
        pl = QVBoxLayout(self._players_group)
        pl.addWidget(scroll)
        self._grid = SetPlayReadOnlyBandGrid()
        self._grid_group = QGroupBox("Up next — band layout")
        gl = QVBoxLayout(self._grid_group)
        gl.addWidget(self._grid, 1)
        self._grid_group.setMinimumHeight(200)

        bottom_horiz = QSplitter(Qt.Orientation.Horizontal)
        bottom_horiz.addWidget(self._players_group)
        bottom_horiz.addWidget(self._grid_group)
        bottom_horiz.setStretchFactor(0, 1)
        bottom_horiz.setStretchFactor(1, 3)

        if not assistant_mode:
            top_row = QSplitter(Qt.Orientation.Horizontal)
            left_panel = QWidget()
            left_lay = QVBoxLayout(left_panel)
            left_lay.setSpacing(8)

            # Top-left upper: name + setlist picker + broadcast + copy code
            self._setlist_name_lbl = QLabel("—")
            self._setlist_name_lbl.setWordWrap(True)
            nf = self._setlist_name_lbl.font()
            nf.setBold(True)
            nf.setPointSize(nf.pointSize() + 2)
            self._setlist_name_lbl.setFont(nf)
            left_lay.addWidget(self._setlist_name_lbl)

            pick_row = QHBoxLayout()
            pick_row.addWidget(QLabel("Setlist:"))
            self._setlist_combo = SetlistPickerCombo()
            self._fill_setlist_combo()
            self._setlist_combo.currentIndexChanged.connect(self._on_setlist_combo_changed)
            pick_row.addWidget(self._setlist_combo, 1)
            self._start_btn = QPushButton("Load set")
            self._start_btn.clicked.connect(self._load_set)
            pick_row.addWidget(self._start_btn)
            left_lay.addLayout(pick_row)

            relay_pick = QHBoxLayout()
            relay_pick.addWidget(QLabel("Relay:"))
            self._relay_combo = QComboBox()
            self._relay_combo.setMinimumWidth(160)
            self._relay_combo.currentIndexChanged.connect(self._on_relay_combo_changed)
            relay_pick.addWidget(self._relay_combo, 1)
            left_lay.addLayout(relay_pick)

            relay_row = QHBoxLayout()
            self._broadcast_cb = QCheckBox("Broadcast (Cloudflare relay)")
            self._broadcast_cb.toggled.connect(self._on_broadcast_toggled)
            relay_row.addWidget(self._broadcast_cb)
            self._copy_code_btn = QPushButton("Copy code")
            self._copy_code_btn.setEnabled(False)
            self._copy_code_btn.clicked.connect(self._copy_room_code)
            relay_row.addWidget(self._copy_code_btn)
            self._leader_reconnect_btn = QPushButton("Reconnect")
            self._leader_reconnect_btn.setToolTip(
                "Reconnect to the relay with the same room after a connection drop."
            )
            self._leader_reconnect_btn.setVisible(False)
            self._leader_reconnect_btn.clicked.connect(self._leader_reconnect_relay)
            relay_row.addWidget(self._leader_reconnect_btn)
            self._room_lbl = QLabel("")
            self._room_lbl.setWordWrap(True)
            relay_row.addWidget(self._room_lbl, 1)
            left_lay.addLayout(relay_row)

            # Top-left mid: setlist info
            self._info_lbl = QLabel("—")
            self._info_lbl.setWordWrap(True)
            self._info_lbl.setAlignment(
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
            )
            left_lay.addWidget(self._info_lbl)

            # Top-left lower: mark whole set first, then advance + auto mark
            mark_row = QHBoxLayout()
            self._mark_set_btn = QPushButton("Mark set as played (all non-skipped)…")
            self._mark_set_btn.clicked.connect(self._mark_set_as_played)
            self._mark_set_btn.setEnabled(False)
            mark_row.addWidget(self._mark_set_btn)
            mark_row.addStretch()
            left_lay.addLayout(mark_row)
            self._adv_btn = QPushButton("Advance song")
            self._adv_btn.setMinimumHeight(48)
            self._adv_btn.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Fixed,
            )
            adv_font = self._adv_btn.font()
            adv_font.setPointSize(adv_font.pointSize() + 3)
            adv_font.setBold(True)
            self._adv_btn.setFont(adv_font)
            self._adv_btn.setStyleSheet(
                f"QPushButton {{ background-color: {COLOR_SURFACE}; color: {COLOR_ON_SURFACE}; "
                f"border: 3px solid {COLOR_OUTLINE}; border-radius: 6px; padding: 10px 16px; }}"
                f"QPushButton:hover {{ border-color: {COLOR_PRIMARY}; }}"
                f"QPushButton:pressed {{ background-color: {COLOR_OUTLINE_VARIANT}; }}"
                f"QPushButton:disabled {{ background-color: {COLOR_SURFACE_VARIANT}; "
                f"color: {COLOR_TEXT_DISABLED}; border-color: {COLOR_OUTLINE_VARIANT}; }}"
            )
            self._adv_btn.clicked.connect(self._advance)
            self._adv_btn.setEnabled(False)
            left_lay.addWidget(self._adv_btn)

            adv_opts = QHBoxLayout()
            self._auto_log = QCheckBox("Mark songs as played automatically")
            self._auto_log.setToolTip(
                "When advancing, record the new current song in the library play history."
            )
            adv_opts.addWidget(self._auto_log)
            adv_opts.addStretch()
            left_lay.addLayout(adv_opts)
            left_lay.addStretch()

            left_panel.setMinimumWidth(300)
            top_row.addWidget(left_panel)
            top_row.addWidget(self._table)
            top_row.setStretchFactor(0, 1)
            top_row.setStretchFactor(1, 3)
        else:
            self._setlist_combo = QComboBox()
            self._setlist_combo.hide()
            self._setlist_name_lbl = None
            self._broadcast_cb = None
            self._room_lbl = None
            self._copy_code_btn = None
            self._auto_log = None
            self._adv_btn = None
            self._mark_set_btn = None

            top_row = QSplitter(Qt.Orientation.Horizontal)
            left_panel = QWidget()
            lv = QVBoxLayout(left_panel)
            lv.setSpacing(6)
            relay_pick = QHBoxLayout()
            relay_pick.addWidget(QLabel("Relay:"))
            self._relay_combo = QComboBox()
            self._relay_combo.setMinimumWidth(160)
            self._relay_combo.currentIndexChanged.connect(self._on_relay_combo_changed)
            relay_pick.addWidget(self._relay_combo, 1)
            lv.addLayout(relay_pick)
            room_row = QHBoxLayout()
            room_row.addWidget(QLabel("Room:"))
            self._room_edit = QComboBox()
            self._room_edit.setEditable(True)
            self._room_edit.setMinimumWidth(120)
            room_row.addWidget(self._room_edit)
            self._connect_btn = QPushButton("Connect")
            self._connect_btn.clicked.connect(self._assistant_connect)
            room_row.addWidget(self._connect_btn)
            self._disconnect_btn = QPushButton("Disconnect")
            self._disconnect_btn.clicked.connect(self._assistant_disconnect)
            self._disconnect_btn.setEnabled(False)
            room_row.addWidget(self._disconnect_btn)
            self._assistant_reconnect_btn = QPushButton("Reconnect")
            self._assistant_reconnect_btn.setToolTip(
                "Connect again with the same room code after a drop."
            )
            self._assistant_reconnect_btn.clicked.connect(self._assistant_reconnect)
            self._assistant_reconnect_btn.setEnabled(False)
            room_row.addWidget(self._assistant_reconnect_btn)
            lv.addLayout(room_row)
            self._info_lbl = QLabel("—")
            self._info_lbl.setWordWrap(True)
            self._info_lbl.setMinimumWidth(180)
            lv.addWidget(self._info_lbl)
            lv.addStretch()
            left_panel.setMinimumWidth(240)
            top_row.addWidget(left_panel)
            top_row.addWidget(self._table)
            top_row.setStretchFactor(0, 1)
            top_row.setStretchFactor(1, 3)

        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY};")
        top_stack = QWidget()
        top_stack_lay = QVBoxLayout(top_stack)
        top_stack_lay.setContentsMargins(0, 0, 0, 0)
        top_stack_lay.setSpacing(6)
        top_stack_lay.addWidget(top_row, 1)
        top_stack_lay.addWidget(self._status_lbl)
        main_vert = QSplitter(Qt.Orientation.Vertical)
        main_vert.addWidget(top_stack)
        main_vert.addWidget(bottom_horiz)
        main_vert.setStretchFactor(0, 2)
        main_vert.setStretchFactor(1, 3)
        main_vert.setChildrenCollapsible(False)
        root.addWidget(main_vert, 1)

        self._fill_relay_combo()

    def refresh_setlist_picker(self) -> None:
        """Reload setlist dropdown from the database (e.g. after setlists change elsewhere)."""
        if self._assistant_mode:
            return
        if hasattr(self, "_setlist_combo"):
            self._fill_setlist_combo()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if hasattr(self, "_relay_combo"):
            self._fill_relay_combo()
        self.refresh_setlist_picker()

    def _fill_relay_combo(self) -> None:
        if not hasattr(self, "_relay_combo"):
            return
        sel = get_set_play_selected_relay_id()
        self._relay_combo.blockSignals(True)
        self._relay_combo.clear()
        relays = get_set_play_relays()
        for r in relays:
            self._relay_combo.addItem(r["name"], r["id"])
        if not relays:
            self._relay_combo.addItem("(add a relay in Settings → Set Playback)", "")
        elif sel:
            idx = self._relay_combo.findData(sel)
            if idx >= 0:
                self._relay_combo.setCurrentIndex(idx)
        self._relay_combo.blockSignals(False)

    def _on_relay_combo_changed(self) -> None:
        if not hasattr(self, "_relay_combo"):
            return
        rid = self._relay_combo.currentData()
        if isinstance(rid, str) and rid:
            set_set_play_selected_relay_id(rid)
        else:
            set_set_play_selected_relay_id(None)

    def _update_leader_reconnect_visibility(self) -> None:
        if self._leader_reconnect_btn is None or self._broadcast_cb is None:
            return
        vis = bool(
            self._broadcast_cb.isChecked()
            and self._relay_code
            and self._relay_leader_token
        )
        self._leader_reconnect_btn.setVisible(vis)
        self._leader_reconnect_btn.setEnabled(vis and not self._relay.is_open())

    def _leader_reconnect_relay(self) -> None:
        if self._assistant_mode or not self._relay_code or not self._relay_leader_token:
            return
        base = get_active_set_play_relay_url()
        if not base:
            QMessageBox.warning(self, "Relay", "Choose a relay in Settings → Set Playback.")
            return
        self._relay.close()
        self._relay.open_leader(base, self._relay_code, self._relay_leader_token)
        self._status_lbl.setText("Reconnecting…")
        self._update_leader_reconnect_visibility()

    def _assistant_reconnect(self) -> None:
        self._assistant_connect()

    def _fill_setlist_combo(self) -> None:
        if not self.app_state:
            return
        preserve_id: int | None = None
        if self._setlist is not None:
            preserve_id = self._setlist.id
        elif self._setlist_combo.currentData() is not None:
            preserve_id = self._setlist_combo.currentData()
        self._setlist_combo.populate(self.app_state.conn, preserve_id=preserve_id)

    def _on_setlist_combo_changed(self) -> None:
        if not self._assistant_mode and self._setlist_name_lbl is not None:
            data = self._setlist_combo.currentData()
            text = self._setlist_combo.currentText()
            if data is None:
                self._setlist_name_lbl.setText("—")
            else:
                self._setlist_name_lbl.setText(text.replace(" [locked]", ""))
        self._session = SetPlaySessionState(order_item_ids=[])
        self._song_rows = []
        self._setlist = None
        if not self._assistant_mode and self._adv_btn:
            self._adv_btn.setEnabled(False)
        if not self._assistant_mode and self._mark_set_btn:
            self._mark_set_btn.setEnabled(False)
        self._refresh_all()

    def _load_set(self) -> None:
        if not self.app_state:
            return
        sid = self._setlist_combo.currentData()
        if not sid:
            QMessageBox.warning(self, "Set Play", "Select a setlist.")
            return
        sl = next((s for s in list_setlists(self.app_state.conn) if s.id == sid), None)
        if not sl:
            QMessageBox.warning(self, "Set Play", "Setlist not found.")
            return
        self._setlist = sl
        self._song_rows = list_setlist_items_with_song_meta(self.app_state.conn, sid)
        self._session = SetPlaySessionState(
            order_item_ids=[r.item.id for r in self._song_rows],
        )
        if self._setlist_name_lbl is not None:
            self._setlist_name_lbl.setText(sl.name)
        if self._adv_btn:
            self._adv_btn.setEnabled(len(self._song_rows) > 0)
        if self._mark_set_btn:
            self._mark_set_btn.setEnabled(len(self._song_rows) > 0)
        self._refresh_all()
        QTimer.singleShot(0, self._grid.fit_cards_to_view)
        self._push_relay_if_leader()

    def _computed_duration_meta(self) -> tuple[int | None, int | None]:
        """(set seconds with switches, remaining vs target) — simplified."""
        if not self._setlist or not self._song_rows:
            return None, None
        total_sec = sum(r.duration_seconds or 0 for r in self._song_rows)
        n = len(self._song_rows)
        delay = self._setlist.default_change_duration_seconds or 0
        switch_sec = delay * (n - 1) if n > 1 else 0
        tw = total_sec + switch_sec
        rem: int | None = None
        if self._setlist.target_duration_seconds and self._setlist.target_duration_seconds > 0:
            rem = int(self._setlist.target_duration_seconds) - tw
        return tw, rem

    def _refresh_info(self) -> None:
        if self._assistant_mode:
            # Filled from relay meta in _apply_remote_snapshot
            return
        if not self._setlist:
            self._info_lbl.setText("Select a setlist and click <b>Load set</b>.")
            return
        tw, rem = self._computed_duration_meta()
        lines = [
            f"<b>Set info</b>",
            f"Date: {self._setlist.set_date or '—'} &nbsp; Time: {self._setlist.set_time or '—'}",
            f"Notes: {(self._setlist.notes or '').strip() or '—'}",
            f"Duration (incl. switches): {_fmt_hhmmss(tw or 0)}"
            if tw is not None
            else "—",
            f"Target: {_fmt_hhmmss(self._setlist.target_duration_seconds or 0)}"
            if self._setlist.target_duration_seconds
            else "Target: —",
            f"Remaining vs target: {_fmt_hhmmss(rem or 0)}" if rem is not None else "",
        ]
        self._info_lbl.setText("<br/>".join(lines))

    def _row_for_item(self, item_id: int) -> SetlistItemSongMetaRow | None:
        for r in self._song_rows:
            if r.item.id == item_id:
                return r
        return None

    def _refresh_table(self) -> None:
        rows = self._song_rows
        self._table.setRowCount(len(rows))
        skip_font = QFont(self._table.font())
        skip_font.setStrikeOut(True)

        for i, r in enumerate(rows):
            iid = r.item.id

            def mk_cb(
                col: int,
                checked: bool,
                on_change,
                ro: bool = False,
            ) -> QWidget:
                w = QWidget()
                h = QHBoxLayout(w)
                h.setContentsMargins(2, 0, 2, 0)
                cb = QCheckBox()
                cb.setChecked(checked)
                if ro:
                    cb.setEnabled(False)
                else:
                    cb.toggled.connect(lambda _=False, c=col, row=i: on_change(row, c))
                h.addWidget(cb, alignment=Qt.AlignmentFlag.AlignCenter)
                return w

            played = iid in self._session.played_item_ids
            cur = self._session.current_item_id == iid
            nx = self._session.next_item_id == iid
            sk = iid in self._session.skipped_item_ids

            if self._assistant_mode:
                self._table.setCellWidget(
                    i,
                    self.COL_PLAYED,
                    mk_cb(self.COL_PLAYED, played, lambda *_: None, ro=True),
                )
                self._table.setCellWidget(
                    i,
                    self.COL_CURRENT,
                    mk_cb(self.COL_CURRENT, cur, lambda *_: None, ro=True),
                )
                self._table.setCellWidget(
                    i,
                    self.COL_NEXT,
                    mk_cb(self.COL_NEXT, nx, lambda *_: None, ro=True),
                )
                self._table.setCellWidget(
                    i,
                    self.COL_SKIP,
                    mk_cb(self.COL_SKIP, sk, lambda *_: None, ro=True),
                )
            else:
                self._table.setCellWidget(
                    i,
                    self.COL_PLAYED,
                    mk_cb(
                        self.COL_PLAYED,
                        played,
                        self._on_checkbox_played,
                        ro=False,
                    ),
                )
                self._table.setCellWidget(
                    i,
                    self.COL_CURRENT,
                    mk_cb(
                        self.COL_CURRENT,
                        cur,
                        self._on_checkbox_current,
                        ro=False,
                    ),
                )
                self._table.setCellWidget(
                    i,
                    self.COL_NEXT,
                    mk_cb(self.COL_NEXT, nx, self._on_checkbox_next, ro=False),
                )
                self._table.setCellWidget(
                    i,
                    self.COL_SKIP,
                    mk_cb(self.COL_SKIP, sk, self._on_checkbox_skip, ro=False),
                )

            t = QTableWidgetItem(r.title)
            t.setFlags(t.flags() & ~Qt.ItemFlag.ItemIsEditable)
            pc = QTableWidgetItem(str(r.part_count))
            pc.setFlags(pc.flags() & ~Qt.ItemFlag.ItemIsEditable)
            d = QTableWidgetItem(_fmt_duration(r.duration_seconds))
            d.setFlags(d.flags() & ~Qt.ItemFlag.ItemIsEditable)
            art = QTableWidgetItem(r.composers or "—")
            art.setFlags(art.flags() & ~Qt.ItemFlag.ItemIsEditable)

            for it in (t, pc, d, art):
                it.setForeground(QColor(COLOR_ON_SURFACE))

            if sk:
                c = QColor(COLOR_ERROR)
                for it in (t, pc, d, art):
                    it.setForeground(c)
                    it.setFont(skip_font)
            elif cur:
                c = QColor("#4caf50")
                for it in (t, pc, d, art):
                    it.setForeground(c)
            elif nx:
                c = QColor("#5c9fd6")
                for it in (t, pc, d, art):
                    it.setForeground(c)
            elif played:
                c = QColor(COLOR_TEXT_SECONDARY)
                for it in (t, pc, d, art):
                    it.setForeground(c)
            else:
                nf = QFont(self._table.font())
                nf.setStrikeOut(False)
                for it in (t, pc, d, art):
                    it.setFont(nf)

            self._table.setItem(i, self.COL_TITLE, t)
            self._table.setItem(i, self.COL_PARTS, pc)
            self._table.setItem(i, self.COL_DUR, d)
            self._table.setItem(i, self.COL_ARTIST, art)

            if self._assistant_mode:
                self._table.setCellWidget(i, self.COL_ACTIONS, QWidget())
            else:
                w = QWidget()
                h = QHBoxLayout(w)
                h.setContentsMargins(2, 0, 2, 0)
                mp = QPushButton("Mark played")
                mp.clicked.connect(lambda _=False, ii=iid: self._action_mark_played(ii))
                lt = QPushButton("Log at time…")
                lt.clicked.connect(lambda _=False, ii=iid: self._action_log_at(ii))
                h.addWidget(mp)
                h.addWidget(lt)
                self._table.setCellWidget(i, self.COL_ACTIONS, w)

    def _on_checkbox_played(self, row: int, _col: int) -> None:
        if self._checkbox_guard or row >= len(self._song_rows):
            return
        w = self._table.cellWidget(row, self.COL_PLAYED)
        cb = w.findChild(QCheckBox, options=Qt.FindChildOption.FindChildrenRecursively) if w else None
        if not cb:
            return
        iid = self._song_rows[row].item.id
        if cb.isChecked():
            self._session.played_item_ids.add(iid)
        else:
            self._session.played_item_ids.discard(iid)
        self._session.revision += 1
        self._after_state_change()

    def _on_checkbox_current(self, row: int, _col: int) -> None:
        if self._checkbox_guard or row >= len(self._song_rows):
            return
        w = self._table.cellWidget(row, self.COL_CURRENT)
        cb = w.findChild(QCheckBox, options=Qt.FindChildOption.FindChildrenRecursively) if w else None
        if not cb or not cb.isChecked():
            if cb and not cb.isChecked():
                if self._session.current_item_id == self._song_rows[row].item.id:
                    apply_exclusive_current(self._session, None)
                    self._after_state_change()
            return
        apply_exclusive_current(self._session, self._song_rows[row].item.id)
        self._after_state_change()

    def _on_checkbox_next(self, row: int, _col: int) -> None:
        if self._checkbox_guard or row >= len(self._song_rows):
            return
        w = self._table.cellWidget(row, self.COL_NEXT)
        cb = w.findChild(QCheckBox, options=Qt.FindChildOption.FindChildrenRecursively) if w else None
        if not cb or not cb.isChecked():
            if cb and not cb.isChecked():
                if self._session.next_item_id == self._song_rows[row].item.id:
                    apply_exclusive_next(self._session, None)
                    self._after_state_change()
            return
        apply_exclusive_next(self._session, self._song_rows[row].item.id)
        self._after_state_change()

    def _on_checkbox_skip(self, row: int, _col: int) -> None:
        if self._checkbox_guard or row >= len(self._song_rows):
            return
        iid = self._song_rows[row].item.id
        toggle_skip(self._session, iid)
        self._after_state_change()

    def _mark_set_as_played(self) -> None:
        """Log play time for every non-skipped song; mark played in session UI."""
        if not self.app_state or not self._setlist:
            return
        to_mark = [
            r
            for r in self._song_rows
            if r.item.id not in self._session.skipped_item_ids
        ]
        if not to_mark:
            QMessageBox.information(self, "Set Play", "No songs to mark (all skipped).")
            return
        dlg = QDialog(self)
        dlg.setWindowTitle("Mark set as played")
        v = QVBoxLayout(dlg)
        v.addWidget(
            QLabel(
                f"This will add a play history entry at the chosen time for "
                f"{len(to_mark)} song(s) (skipped rows excluded)."
            )
        )
        dt = QDateTimeEdit()
        dt.setCalendarPopup(True)
        v.addWidget(QLabel("Played at (converted to UTC for storage):"))
        v.addWidget(dt)
        bb = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
        )
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        v.addWidget(bb)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        qdt = dt.dateTime().toUTC()
        iso = qdt.toString("yyyy-MM-ddTHH:mm:ss.zzzZ")
        for r in to_mark:
            log_play_at(
                self.app_state.conn,
                r.item.song_id,
                iso,
                context_setlist_id=self._setlist.id,
            )
        for r in to_mark:
            self._session.played_item_ids.add(r.item.id)
        self._session.revision += 1
        self._after_state_change()
        QMessageBox.information(
            self,
            "Set Play",
            f"Recorded play time for {len(to_mark)} song(s).",
        )

    def _advance(self) -> None:
        if self._session.next_item_id is None:
            self._status_lbl.setText("Choose a Next song before advancing.")
            return
        ok = advance_song(self._session)
        if not ok:
            return
        if (
            self._auto_log
            and self._auto_log.isChecked()
            and self.app_state
            and self._session.current_item_id is not None
            and self._setlist
        ):
            row = self._row_for_item(self._session.current_item_id)
            if row:
                log_play(
                    self.app_state.conn,
                    row.item.song_id,
                    context_setlist_id=self._setlist.id,
                )
        self._after_state_change()

    def _action_mark_played(self, item_id: int) -> None:
        if not self.app_state or not self._setlist:
            return
        row = self._row_for_item(item_id)
        if row:
            log_play(
                self.app_state.conn,
                row.item.song_id,
                context_setlist_id=self._setlist.id,
            )
        QMessageBox.information(self, "Set Play", "Marked as played in library.")

    def _action_log_at(self, item_id: int) -> None:
        if not self.app_state or not self._setlist:
            return
        row = self._row_for_item(item_id)
        if not row:
            return
        dlg = QDialog(self)
        dlg.setWindowTitle("Log play at time")
        v = QVBoxLayout(dlg)
        dt = QDateTimeEdit()
        dt.setCalendarPopup(True)
        v.addWidget(dt)
        bb = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
        )
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        v.addWidget(bb)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        qdt = dt.dateTime().toUTC()
        iso = qdt.toString("yyyy-MM-ddTHH:mm:ss.zzzZ")
        log_play_at(
            self.app_state.conn,
            row.item.song_id,
            iso,
            context_setlist_id=self._setlist.id,
        )
        QMessageBox.information(self, "Set Play", "Play logged at chosen time.")

    def _build_layout_cards(self) -> list[LayoutCard]:
        if (
            not self.app_state
            or not self._setlist
            or not self._setlist.band_layout_id
        ):
            return []
        next_row = (
            self._row_for_item(self._session.next_item_id)
            if self._session.next_item_id
            else None
        )
        cur_row = (
            self._row_for_item(self._session.current_item_id)
            if self._session.current_item_id
            else None
        )
        order = self._session.order_item_ids
        right_id: int | None = None
        if self._session.next_item_id and next_row:
            try:
                ni = order.index(self._session.next_item_id)
            except ValueError:
                ni = -1
            right_id = scan_next_item_id(
                order,
                self._session.skipped_item_ids,
                after_index=ni,
            )
        right_row = self._row_for_item(right_id) if right_id else None
        return build_set_play_layout_cards(
            self.app_state.conn,
            band_layout_id=self._setlist.band_layout_id,
            next_row=next_row,
            current_row=cur_row,
            right_row=right_row,
            setlist_rows=self._song_rows,
        )

    def _refresh_grid(self) -> None:
        if self._assistant_mode:
            self._grid.set_cards(list(self._layout_cards))
            self._grid.set_highlight_player_ids(self._highlight_players)
            return
        self._layout_cards = self._build_layout_cards()
        self._grid.set_cards(list(self._layout_cards))
        self._grid.set_highlight_player_ids(self._highlight_players)

    def _refresh_players(self) -> None:
        while self._players_inner_layout.count():
            it = self._players_inner_layout.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        if self._assistant_mode:
            players: dict[int, str] = {}
            for c in self._layout_cards:
                players[c.player_id] = c.player_name
        elif self.app_state and self._setlist and self._setlist.band_layout_id:
            from ..db.player_repo import list_players
            from ..db.band_repo import list_layout_slots

            slots = list_layout_slots(self.app_state.conn, self._setlist.band_layout_id)
            pmap = {p.id: p.name for p in list_players(self.app_state.conn)}
            players = {s.player_id: pmap.get(s.player_id, str(s.player_id)) for s in slots}
        else:
            players = {}
        for pid, name in sorted(players.items(), key=lambda x: x[1].lower()):
            cb = QCheckBox(name)
            cb.setChecked(pid in self._highlight_players)

            def on_toggled(checked: bool, p: int = pid) -> None:
                if checked:
                    self._highlight_players.add(p)
                else:
                    self._highlight_players.discard(p)
                self._grid.set_highlight_player_ids(self._highlight_players)

            cb.toggled.connect(on_toggled)
            self._players_inner_layout.addWidget(cb)
        self._players_inner_layout.addStretch()

    def _refresh_all(self) -> None:
        self._checkbox_guard = True
        self._refresh_info()
        self._refresh_table()
        self._checkbox_guard = False
        self._refresh_players()
        self._refresh_grid()

    def _after_state_change(self) -> None:
        self._checkbox_guard = True
        self._refresh_table()
        self._checkbox_guard = False
        self._refresh_grid()
        self._push_relay_if_leader()

    def _push_relay_if_leader(self) -> None:
        if self._assistant_mode or not self._relay.is_open():
            return
        if not self.app_state or not self._setlist:
            return
        tw, _rem = self._computed_duration_meta()
        payload = snapshot_from_leader(
            self._session,
            self._setlist,
            self._song_rows,
            computed_duration_seconds=tw,
            layout_cards=self._layout_cards,
        )
        self._last_pushed_revision = self._session.revision
        self._relay.send_snapshot(payload)

    def _on_broadcast_toggled(self, on: bool) -> None:
        if not on:
            self._relay.close()
            self._relay_code = None
            self._relay_leader_token = None
            if self._room_lbl:
                self._room_lbl.setText("")
            if self._copy_code_btn:
                self._copy_code_btn.setEnabled(False)
            self._update_leader_reconnect_visibility()
            return
        base = get_active_set_play_relay_url()
        if not base:
            QMessageBox.warning(
                self,
                "Relay",
                "Add a relay in Settings → Set Playback (use wss:// from your Worker).",
            )
            if self._broadcast_cb:
                self._broadcast_cb.blockSignals(True)
                self._broadcast_cb.setChecked(False)
                self._broadcast_cb.blockSignals(False)
            return
        try:
            code, token = create_relay_room(base)
        except (urllib.error.URLError, OSError, KeyError, ValueError) as e:
            QMessageBox.warning(self, "Relay", f"Could not create room: {e}")
            if self._broadcast_cb:
                self._broadcast_cb.blockSignals(True)
                self._broadcast_cb.setChecked(False)
                self._broadcast_cb.blockSignals(False)
            return
        self._relay_code = code
        self._relay_leader_token = token
        if self._room_lbl:
            self._room_lbl.setText(f"Code: <b>{code}</b> (share with assistants)")
        if self._copy_code_btn:
            self._copy_code_btn.setEnabled(True)
        self._relay.open_leader(base, code, token)
        QTimer.singleShot(500, self._push_relay_if_leader)
        self._update_leader_reconnect_visibility()

    def _on_relay_connected(self) -> None:
        self._status_lbl.setText("Relay connected.")
        self._push_relay_if_leader()
        self._update_leader_reconnect_visibility()
        if self._assistant_mode and hasattr(self, "_assistant_reconnect_btn"):
            self._assistant_reconnect_btn.setEnabled(True)

    def _on_relay_disconnected(self) -> None:
        if not self._assistant_mode:
            self._status_lbl.setText("Relay disconnected.")
            self._update_leader_reconnect_visibility()
        else:
            self._disconnect_btn.setEnabled(False)
            if hasattr(self, "_assistant_reconnect_btn"):
                code = (self._room_edit.currentText() or "").strip()
                self._assistant_reconnect_btn.setEnabled(len(code) >= 5)

    def _on_relay_error(self, msg: str) -> None:
        self._status_lbl.setText(f"Relay: {msg}")

    def _on_relay_state(self, data: dict[str, Any]) -> None:
        if not self._assistant_mode:
            if int(data.get("revision") or 0) <= self._last_pushed_revision:
                return
        if data.get("type") != STATE_TYPE:
            return
        self._apply_remote_snapshot(data)

    def _copy_room_code(self) -> None:
        if self._relay_code:
            from PySide6.QtWidgets import QApplication

            QApplication.clipboard().setText(self._relay_code)

    def _assistant_connect(self) -> None:
        base = get_active_set_play_relay_url()
        if not base:
            QMessageBox.warning(self, "Relay", "Add a relay in Settings → Set Playback.")
            return
        code = (self._room_edit.currentText() or "").strip().upper()
        if len(code) < 5:
            QMessageBox.warning(self, "Relay", "Enter the room code.")
            return
        self._relay.close()
        self._relay.open_assistant(base, code)
        self._disconnect_btn.setEnabled(True)
        if hasattr(self, "_assistant_reconnect_btn"):
            self._assistant_reconnect_btn.setEnabled(True)
        self._status_lbl.setText("Connecting…")

    def _assistant_disconnect(self) -> None:
        self._relay.close()
        self._disconnect_btn.setEnabled(False)
        if hasattr(self, "_assistant_reconnect_btn"):
            code = (self._room_edit.currentText() or "").strip()
            self._assistant_reconnect_btn.setEnabled(len(code) >= 5)
        self._status_lbl.setText("Disconnected.")

    def _apply_remote_snapshot(self, data: dict[str, Any]) -> None:
        st, meta, row_dicts, card_dicts = apply_snapshot_to_session(data)
        self._session = st
        now = ""
        fake_rows: list[SetlistItemSongMetaRow] = []
        for rd in row_dicts:
            item = SetlistItemRow(
                id=int(rd["item_id"]),
                setlist_id=int(data.get("setlist_id") or 0),
                song_id=int(rd["song_id"]),
                position=int(rd.get("position") or 0),
                override_change_duration_seconds=None,
                song_layout_id=None,
                created_at=now,
                updated_at=now,
            )
            fake_rows.append(
                SetlistItemSongMetaRow(
                    item=item,
                    title=str(rd.get("title") or ""),
                    composers=str(rd.get("artist") or "—"),
                    duration_seconds=rd.get("duration_seconds"),
                    part_count=int(rd.get("part_count") or 0),
                    parts_json=None,
                )
            )
        self._song_rows = fake_rows
        self._layout_cards = layout_cards_from_payload(card_dicts)
        self._setlist = None
        lines = [
            f"<b>{meta.get('name', 'Set')}</b>",
            f"Date: {meta.get('set_date') or '—'}  Time: {meta.get('set_time') or '—'}",
            f"Notes: {(meta.get('notes') or '').strip() or '—'}",
        ]
        tw = meta.get("computed_duration_seconds")
        if tw is not None:
            lines.append(f"Duration (incl. switches): {_fmt_hhmmss(int(tw))}")
        self._info_lbl.setText("<br/>".join(lines))
        self._status_lbl.setText(f"Synced (rev {self._session.revision}).")
        self._refresh_all()
        QTimer.singleShot(0, self._grid.fit_cards_to_view)

