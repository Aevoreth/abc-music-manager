"""
Setlist manager: band-style splitter, song table with live metadata, part assignments.
REQUIREMENTS §6.
"""

from __future__ import annotations

import json

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QPushButton,
    QLabel,
    QLineEdit,
    QComboBox,
    QCheckBox,
    QSpinBox,
    QMessageBox,
    QInputDialog,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QAbstractItemView,
    QHeaderView,
    QDateEdit,
    QTimeEdit,
    QScrollArea,
)
from PySide6.QtCore import Qt, QDate, QTime, QTimer, QMimeData
from PySide6.QtGui import QColor, QFont, QDrag

from ..services.app_state import AppState
from ..services.preferences import (
    get_setlists_splitter_state,
    get_setlists_editor_splitter_state,
    get_setlists_top_split_state,
    get_setlists_songs_table_header_state,
    set_setlists_top_split_state,
    set_setlists_songs_table_header_state,
)
from ..db import list_library_songs
from ..db.setlist_repo import (
    list_setlists,
    add_setlist,
    update_setlist,
    delete_setlist,
    list_setlist_items_with_song_meta,
    add_setlist_item,
    update_setlist_item,
    remove_setlist_item,
    reorder_setlist_items,
    get_setlist_band_assignments,
    SetlistRow,
    SetlistItemSongMetaRow,
)
from ..db.song_layout_repo import (
    list_song_layouts_for_song_and_band,
    add_song_layout,
    set_song_layout_assignment,
    get_song_layout_assignments,
)
from ..db.band_repo import list_all_band_layouts, list_layout_slots, list_band_members
from ..db.player_repo import list_player_instruments_bulk
from .setlist_band_assignment_panel import SetlistBandAssignmentPanel
from .theme import COLOR_ON_SURFACE


def _fmt_duration(sec: int | None) -> str:
    if sec is None or sec <= 0:
        return "—"
    m, s = divmod(int(sec), 60)
    if m >= 60:
        h, m = divmod(m, 60)
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def _fmt_hhmmss(sec: int) -> str:
    """Format seconds as H:mm:ss, m:ss, or s (no leading zeros). Handles negative values."""
    sec = int(sec)
    neg = sec < 0
    sec = abs(sec)
    h, r = divmod(sec, 3600)
    m, s = divmod(r, 60)
    if h > 0:
        out = f"{h}:{m:02d}:{s:02d}"
    elif m > 0:
        out = f"{m}:{s:02d}"
    else:
        out = str(s)
    return f"-{out}" if neg else out


_MIME_ROW = "application/x-setlist-song-row"


class SetlistSongsTable(QTableWidget):
    """Table with vertical-only drag-drop. Rows move visually during drag."""

    rowReordered = None  # Set by parent: callable() -> None, persists current order

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        self.setDragDropOverwriteMode(False)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setDropIndicatorShown(True)
        self._drag_row: int = -1

    def startDrag(self, supportedActions) -> None:
        row = self.currentRow()
        if row < 0:
            return
        self._drag_row = row
        mime = QMimeData()
        mime.setData(_MIME_ROW, str(row).encode("utf-8"))
        indexes = [self.model().index(row, c) for c in range(self.model().columnCount())]
        model_mime = self.model().mimeData(indexes)
        if model_mime:
            model_mime.setData(_MIME_ROW, str(row).encode("utf-8"))
            mime = model_mime
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.exec(Qt.DropAction.MoveAction)
        self._drag_row = -1

    def _move_row_visually(self, from_row: int, to_row: int) -> None:
        """Move a row in the table, preserving the cell widget."""
        if from_row == to_row or from_row < 0 or to_row < 0:
            return
        n = self.rowCount()
        if from_row >= n or to_row > n:
            return
        w = self.cellWidget(from_row, 5)
        if w:
            w.setParent(None)
        items = [self.takeItem(from_row, c) for c in range(self.columnCount())]
        self.removeRow(from_row)
        if to_row > from_row:
            to_row -= 1
        self.insertRow(to_row)
        for c, it in enumerate(items):
            self.setItem(to_row, c, it)
        if w:
            self.setCellWidget(to_row, 5, w)
        self._drag_row = to_row
        self.selectRow(to_row)

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasFormat(_MIME_ROW):
            event.acceptProposedAction()
            super().dragEnterEvent(event)
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:
        if not event.mimeData().hasFormat(_MIME_ROW) or self._drag_row < 0:
            event.ignore()
            return
        event.acceptProposedAction()
        pos = event.position().toPoint()
        idx = self.indexAt(pos)
        row = idx.row()
        if row >= 0:
            rect = self.visualRect(idx)
            if pos.y() > rect.center().y():
                drop_row = row + 1
            else:
                drop_row = row
        else:
            drop_row = self.rowCount()
        if drop_row != self._drag_row:
            self._move_row_visually(self._drag_row, drop_row)
        super().dragMoveEvent(event)

    def dropEvent(self, event) -> None:
        mime = event.mimeData()
        if not mime.hasFormat(_MIME_ROW):
            event.ignore()
            return
        event.accept()
        if self.rowReordered:
            self.rowReordered()


class SetlistsView(QWidget):
    def __init__(self, app_state: AppState, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.app_state = app_state
        self._selected_setlist_id: int | None = None
        self._loaded_name = ""
        self._loaded_notes = ""
        self._loaded_band_layout_id: int | None = None
        self._loaded_locked = False
        self._loaded_default_dur: int | None = None
        self._loaded_set_date: str | None = None
        self._loaded_set_time: str | None = None
        self._loaded_target_dur: int | None = None
        self._filling_songs = False
        self._splitter_restored = False
        self._editor_splitter_restored = False
        self._top_split_restored = False
        self._songs_table_header_restored = False
        self._songs_header_save_timer = QTimer(self)
        self._songs_header_save_timer.setSingleShot(True)
        self._songs_header_save_timer.timeout.connect(self._save_songs_table_header_state)
        self._top_split_save_timer = QTimer(self)
        self._top_split_save_timer.setSingleShot(True)
        self._top_split_save_timer.timeout.connect(lambda: set_setlists_top_split_state(self.top_split.sizes()))

        root = QVBoxLayout(self)

        add_btn = QPushButton("Add setlist")
        add_btn.clicked.connect(self._add_setlist)
        fm = add_btn.fontMetrics()
        add_btn.setFixedWidth(fm.horizontalAdvance("Add setlist") + 24)
        root.addWidget(add_btn)

        self.setlists_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.setlist_list = QListWidget()
        self.setlist_list.setWordWrap(True)
        self.setlist_list.setMinimumWidth(120)
        self.setlist_list.setMaximumWidth(320)
        self.setlist_list.currentRowChanged.connect(self._on_setlist_selected)
        self.setlists_splitter.addWidget(self.setlist_list)

        editor = QWidget()
        editor_layout = QVBoxLayout(editor)

        self.top_split = QSplitter(Qt.Orientation.Horizontal)
        meta_col = QWidget()
        mv = QVBoxLayout(meta_col)

        btn_row = QHBoxLayout()
        self.save_btn = QPushButton("Save")
        self.save_btn.setFixedWidth(self.save_btn.fontMetrics().horizontalAdvance("Save") + 24)
        self.save_btn.clicked.connect(self._save_setlist)
        self.delete_btn = QPushButton("Delete")
        self.delete_btn.setFixedWidth(self.delete_btn.fontMetrics().horizontalAdvance("Delete") + 24)
        self.delete_btn.clicked.connect(self._delete_selected_setlist)
        btn_row.addWidget(self.save_btn)
        btn_row.addWidget(self.delete_btn)
        btn_row.addStretch()
        mv.addLayout(btn_row)

        mv.addWidget(QLabel("Name:"))
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Setlist name")
        mv.addWidget(self.name_edit)

        mv.addWidget(QLabel("Band layout (optional — required for play & part UI):"))
        self.band_layout_combo = QComboBox()
        self.band_layout_combo.currentIndexChanged.connect(self._on_band_layout_combo_changed)
        mv.addWidget(self.band_layout_combo)

        dt_row = QHBoxLayout()
        dt_row.addWidget(QLabel("Set date:"))
        self.set_date_edit = QDateEdit()
        self.set_date_edit.setCalendarPopup(True)
        dt_row.addWidget(self.set_date_edit)
        dt_row.addWidget(QLabel("Set time:"))
        self.set_time_edit = QTimeEdit()
        self.set_time_edit.setDisplayFormat("HH:mm")
        dt_row.addWidget(self.set_time_edit)
        dt_row.addStretch()
        mv.addLayout(dt_row)

        dur_row = QHBoxLayout()
        dur_row.addWidget(QLabel("Set length:"))
        self.target_duration_edit = QTimeEdit()
        self.target_duration_edit.setDisplayFormat("H:mm")
        self.target_duration_edit.setTime(QTime(0, 0))
        self.target_duration_edit.timeChanged.connect(self._update_duration_computed)
        dur_row.addWidget(self.target_duration_edit)
        dur_row.addWidget(QLabel("Song Switch Delay (s):"))
        self.default_duration_spin = QSpinBox()
        self.default_duration_spin.setRange(0, 300)
        self.default_duration_spin.setSpecialValueText("—")
        self.default_duration_spin.valueChanged.connect(self._update_duration_computed)
        dur_row.addWidget(self.default_duration_spin)
        dur_row.addStretch()
        mv.addLayout(dur_row)

        computed_row = QHBoxLayout()
        self.set_duration_lbl = QLabel("Set Duration: —")
        f = self.set_duration_lbl.font()
        f.setWeight(QFont.Weight.Bold)
        self.set_duration_lbl.setFont(f)
        computed_row.addWidget(self.set_duration_lbl)
        self.set_duration_with_switches_lbl = QLabel("With Part Switching: —")
        self.set_duration_with_switches_lbl.setFont(f)
        computed_row.addWidget(self.set_duration_with_switches_lbl)
        computed_row.addStretch()
        mv.addLayout(computed_row)
        self.remaining_set_time_lbl = QLabel("Remaining: —")
        self.remaining_set_time_lbl.setFont(f)
        mv.addWidget(self.remaining_set_time_lbl)

        mv.addWidget(QLabel("Notes:"))
        self.notes_edit = QPlainTextEdit()
        self.notes_edit.setPlaceholderText("Notes")
        self.notes_edit.setFixedHeight(72)
        self.notes_edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        mv.addWidget(self.notes_edit)

        self.locked_check = QCheckBox("Locked (excluded from Add to Set)")
        mv.addWidget(self.locked_check)
        mv.addStretch()
        meta_scroll = QScrollArea()
        meta_scroll.setWidgetResizable(True)
        meta_scroll.setWidget(meta_col)
        meta_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        meta_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.top_split.addWidget(meta_scroll)

        songs_col = QWidget()
        sv = QVBoxLayout(songs_col)
        sh = QHBoxLayout()
        sh.addWidget(QLabel("Songs in set (↑↓ or drag rows to reorder):"))
        sh.addStretch()
        add_song_btn = QPushButton("Add song")
        add_song_btn.clicked.connect(self._add_item)
        sh.addWidget(add_song_btn)
        sv.addLayout(sh)

        self.songs_table = SetlistSongsTable()
        self.songs_table.setColumnCount(6)
        self.songs_table.setHorizontalHeaderLabels(["", "Title", "Parts", "Duration", "Artist", "Actions"])
        self.songs_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.songs_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        for col in range(6):
            self.songs_table.horizontalHeader().setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
        self.songs_table.horizontalHeader().setMinimumSectionSize(20)
        self.songs_table.horizontalHeader().resizeSection(0, 24)
        fm = self.songs_table.fontMetrics()
        row_height = fm.lineSpacing() + 8
        self.songs_table.verticalHeader().setDefaultSectionSize(row_height)
        self.songs_table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self.songs_table.verticalHeader().setSectionsMovable(False)
        self.songs_table.verticalHeader().setSectionsClickable(True)
        self.songs_table.rowReordered = self._on_song_row_dragged
        self.songs_table.itemSelectionChanged.connect(self._on_song_selection_changed)
        self.songs_table.horizontalHeader().sectionResized.connect(self._on_songs_header_section_resized)
        songs_scroll = QScrollArea()
        songs_scroll.setWidgetResizable(True)
        songs_scroll.setWidget(songs_col)
        songs_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        songs_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        sv.addWidget(self.songs_table, 1)
        self.top_split.addWidget(songs_scroll)
        self.top_split.setStretchFactor(1, 2)
        self.top_split.splitterMoved.connect(lambda: self._top_split_save_timer.start(150))

        self.assignment_panel = SetlistBandAssignmentPanel(app_state)
        self.assignment_panel.assignment_changed.connect(self._on_assignment_changed)

        self.editor_splitter = QSplitter(Qt.Orientation.Vertical)
        self.editor_splitter.addWidget(self.top_split)
        self.editor_splitter.addWidget(self.assignment_panel)
        self.editor_splitter.setStretchFactor(0, 1)
        self.editor_splitter.setStretchFactor(1, 2)
        editor_layout.addWidget(self.editor_splitter)

        self.setlists_splitter.addWidget(editor)
        self.setlists_splitter.setStretchFactor(1, 1)
        root.addWidget(self.setlists_splitter)

        self._editor_enabled = False
        self._set_editor_enabled(False)

    def _set_editor_enabled(self, on: bool) -> None:
        self._editor_enabled = on
        for w in (
            self.save_btn,
            self.delete_btn,
            self.name_edit,
            self.band_layout_combo,
            self.set_date_edit,
            self.set_time_edit,
            self.target_duration_edit,
            self.notes_edit,
            self.locked_check,
            self.default_duration_spin,
            self.songs_table,
            self.set_duration_lbl,
            self.set_duration_with_switches_lbl,
            self.remaining_set_time_lbl,
        ):
            w.setEnabled(on)
        if not on:
            self.assignment_panel.clear()

    def select_setlist_by_id(self, setlist_id: int) -> None:
        self._refresh_setlist_names()
        for i in range(self.setlist_list.count()):
            if self.setlist_list.item(i).data(Qt.ItemDataRole.UserRole) == setlist_id:
                self.setlist_list.setCurrentRow(i)
                return

    def _refresh_setlist_names(self) -> None:
        cur_id = None
        row = self.setlist_list.currentRow()
        if row >= 0 and self.setlist_list.item(row):
            cur_id = self.setlist_list.item(row).data(Qt.ItemDataRole.UserRole)
        self.setlist_list.clear()
        for s in list_setlists(self.app_state.conn):
            it = QListWidgetItem(s.name)
            it.setData(Qt.ItemDataRole.UserRole, s.id)
            self.setlist_list.addItem(it)
        if cur_id is not None:
            for i in range(self.setlist_list.count()):
                if self.setlist_list.item(i).data(Qt.ItemDataRole.UserRole) == cur_id:
                    self.setlist_list.setCurrentRow(i)
                    return
        if self.setlist_list.count() and self.setlist_list.currentRow() < 0:
            self.setlist_list.setCurrentRow(0)

    def _on_setlist_selected(self, row: int) -> None:
        if row < 0:
            self._selected_setlist_id = None
            self._set_editor_enabled(False)
            self._update_duration_computed()
            return
        item = self.setlist_list.item(row)
        if not item:
            return
        sid = item.data(Qt.ItemDataRole.UserRole)
        self._selected_setlist_id = sid
        s = next(x for x in list_setlists(self.app_state.conn) if x.id == sid)
        self._set_editor_enabled(True)
        self.name_edit.setText(s.name)
        self.notes_edit.setPlainText(s.notes or "")
        self.locked_check.setChecked(s.locked)
        self.default_duration_spin.setValue(s.default_change_duration_seconds or 0)
        self._load_band_layout_combo()
        for i in range(self.band_layout_combo.count()):
            if self.band_layout_combo.itemData(i) == s.band_layout_id:
                self.band_layout_combo.setCurrentIndex(i)
                break
        else:
            self.band_layout_combo.setCurrentIndex(0)
        self._loaded_name = s.name
        self._loaded_notes = s.notes or ""
        self._loaded_band_layout_id = s.band_layout_id
        self._loaded_locked = s.locked
        self._loaded_default_dur = s.default_change_duration_seconds
        self._loaded_set_date = s.set_date
        self._loaded_set_time = s.set_time
        self._loaded_target_dur = s.target_duration_seconds
        if s.set_date:
            parts = s.set_date.split("-")
            if len(parts) == 3:
                self.set_date_edit.setDate(QDate(int(parts[0]), int(parts[1]), int(parts[2])))
            else:
                self.set_date_edit.setDate(QDate.currentDate())
        else:
            self.set_date_edit.setDate(QDate.currentDate())
        if s.set_time:
            parts = s.set_time.split(":")
            h = int(parts[0]) if parts else 0
            m = int(parts[1]) if len(parts) > 1 else 0
            self.set_time_edit.setTime(QTime(h, m))
        else:
            self.set_time_edit.setTime(QTime(19, 0))
        if s.target_duration_seconds and s.target_duration_seconds > 0:
            self.target_duration_edit.setTime(QTime(0, 0).addSecs(s.target_duration_seconds))
        else:
            self.target_duration_edit.setTime(QTime(0, 0))
        self._refresh_songs_table()

    def _load_band_layout_combo(self) -> None:
        self.band_layout_combo.blockSignals(True)
        self.band_layout_combo.clear()
        self.band_layout_combo.addItem("(none — draft)", None)
        for layout_id, layout_name, band_name in list_all_band_layouts(self.app_state.conn):
            self.band_layout_combo.addItem(f"{band_name} — {layout_name}", layout_id)
        self.band_layout_combo.blockSignals(False)

    def _on_band_layout_combo_changed(self) -> None:
        self._refresh_songs_table()
        self._refresh_assignment_panel()

    def _refresh_songs_table(self, select_item_id: int | None = None) -> None:
        if not self._selected_setlist_id:
            self.songs_table.setRowCount(0)
            return
        self._filling_songs = True
        self.songs_table.verticalHeader().blockSignals(True)
        rows = list_setlist_items_with_song_meta(self.app_state.conn, self._selected_setlist_id)
        sl = next(s for s in list_setlists(self.app_state.conn) if s.id == self._selected_setlist_id)
        slots = list_layout_slots(self.app_state.conn, sl.band_layout_id) if sl.band_layout_id else []
        pids = [s.player_id for s in slots]
        bulk = list_player_instruments_bulk(self.app_state.conn, pids) if pids else {}

        self.songs_table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            err = self._song_has_error(sl, r, bulk, slots)
            flag = QTableWidgetItem("\u26a0" if err else "")
            flag.setForeground(QColor("#ff4444") if err else QColor(COLOR_ON_SURFACE))
            f = QFont()
            f.setPointSize(f.pointSize() + 4)
            f.setWeight(QFont.Weight.Bold)
            flag.setFont(f)
            flag.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            flag.setFlags(flag.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.songs_table.setItem(i, 0, flag)

            t = QTableWidgetItem(r.title)
            t.setData(Qt.ItemDataRole.UserRole, r.item.id)
            t.setFlags(t.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.songs_table.setItem(i, 1, t)

            pc = QTableWidgetItem(str(r.part_count))
            pc.setFlags(pc.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.songs_table.setItem(i, 2, pc)

            dur = QTableWidgetItem(_fmt_duration(r.duration_seconds))
            dur.setFlags(dur.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.songs_table.setItem(i, 3, dur)

            art = QTableWidgetItem(r.composers or "—")
            art.setFlags(art.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.songs_table.setItem(i, 4, art)

            w = QWidget()
            h = QHBoxLayout(w)
            h.setContentsMargins(2, 0, 2, 0)
            _btn_style = "padding: 0 4px; font-size: 11px; min-height: 0;"
            fm = self.songs_table.fontMetrics()
            up_btn = QPushButton("\u2191")
            up_btn.setStyleSheet(_btn_style)
            up_btn.setFixedWidth(fm.horizontalAdvance("\u2191") + 8)
            up_btn.setFixedHeight(18)
            up_btn.clicked.connect(lambda checked=False, iid=r.item.id: self._move_song(iid, -1))
            down_btn = QPushButton("\u2193")
            down_btn.setStyleSheet(_btn_style)
            down_btn.setFixedWidth(fm.horizontalAdvance("\u2193") + 8)
            down_btn.setFixedHeight(18)
            down_btn.clicked.connect(lambda checked=False, iid=r.item.id: self._move_song(iid, 1))
            rem_btn = QPushButton("Remove")
            rem_btn.setStyleSheet(_btn_style)
            rem_btn.setFixedWidth(fm.horizontalAdvance("Remove") + 12)
            rem_btn.setFixedHeight(18)
            rem_btn.clicked.connect(lambda checked=False, it=r.item: self._remove_item(it))
            h.addWidget(up_btn)
            h.addWidget(down_btn)
            h.addWidget(rem_btn)
            self.songs_table.setCellWidget(i, 5, w)

        self.songs_table.verticalHeader().blockSignals(False)
        self._filling_songs = False
        if rows:
            sel = 0
            if select_item_id is not None:
                for j, rr in enumerate(rows):
                    if rr.item.id == select_item_id:
                        sel = j
                        break
            self.songs_table.selectRow(sel)
            self._refresh_assignment_panel()
        else:
            self.assignment_panel.clear()
        self._update_duration_computed()

    def _update_duration_computed(self) -> None:
        """Update Set Duration, With Part Switching, and Remaining labels."""
        if not self._selected_setlist_id:
            self.set_duration_lbl.setText("Set Duration: —")
            self.set_duration_with_switches_lbl.setText("With Part Switching: —")
            self.remaining_set_time_lbl.setText("Remaining: —")
            return
        rows = list_setlist_items_with_song_meta(self.app_state.conn, self._selected_setlist_id)
        total_sec = sum(r.duration_seconds or 0 for r in rows)
        n = len(rows)
        delay = self.default_duration_spin.value() if self.default_duration_spin.value() >= 0 else 0
        switch_sec = delay * (n - 1) if n > 1 else 0
        total_with_switches = total_sec + switch_sec

        self.set_duration_lbl.setText(f"Set Duration: {_fmt_hhmmss(total_sec)}")
        self.set_duration_with_switches_lbl.setText(f"With Part Switching: {_fmt_hhmmss(total_with_switches)}")

        set_length_sec = QTime(0, 0).secsTo(self.target_duration_edit.time())
        if set_length_sec > 0:
            remaining = set_length_sec - total_with_switches
            self.remaining_set_time_lbl.setText(f"Remaining: {_fmt_hhmmss(remaining)}")
        else:
            self.remaining_set_time_lbl.setText("Remaining: —")

    def _song_has_error(
        self,
        sl: SetlistRow,
        r: SetlistItemSongMetaRow,
        bulk: dict[int, set[int]],
        slots: list,
    ) -> bool:
        if not sl.band_layout_id:
            return False
        if r.item.song_layout_id is None:
            return True
        overrides = get_setlist_band_assignments(self.app_state.conn, r.item.id)
        layout = {
            a.player_id: a.part_number
            for a in get_song_layout_assignments(self.app_state.conn, r.item.song_layout_id)
        }
        parts = json.loads(r.parts_json) if r.parts_json else []
        pbn = {int(p["part_number"]): p for p in parts}
        for s in slots:
            pid = s.player_id
            pn = overrides[pid] if pid in overrides else layout.get(pid)
            if pn is None:
                continue
            pm = pbn.get(pn)
            if not pm:
                continue
            iid = pm.get("instrument_id")
            if iid and iid not in bulk.get(pid, set()):
                return True
        return False

    def _move_song(self, item_id: int, delta: int) -> None:
        if not self._selected_setlist_id or delta not in (-1, 1):
            return
        rows = list_setlist_items_with_song_meta(self.app_state.conn, self._selected_setlist_id)
        ids = [r.item.id for r in rows]
        try:
            idx = ids.index(item_id)
        except ValueError:
            return
        j = idx + delta
        if j < 0 or j >= len(ids):
            return
        ids[idx], ids[j] = ids[j], ids[idx]
        reorder_setlist_items(self.app_state.conn, self._selected_setlist_id, ids)
        self._refresh_songs_table(select_item_id=item_id)

    def _on_song_row_dragged(self) -> None:
        """Persist current table order after drag-drop (rows already moved visually)."""
        if self._filling_songs or not self._selected_setlist_id:
            return
        ids = []
        for r in range(self.songs_table.rowCount()):
            it = self.songs_table.item(r, 1)
            if it:
                ids.append(it.data(Qt.ItemDataRole.UserRole))
        if len(ids) != self.songs_table.rowCount():
            return
        cr = self.songs_table.currentRow()
        sel_id = self.songs_table.item(cr, 1).data(Qt.ItemDataRole.UserRole) if cr >= 0 and self.songs_table.item(cr, 1) else None
        reorder_setlist_items(self.app_state.conn, self._selected_setlist_id, ids)
        self._refresh_songs_table(select_item_id=sel_id)

    def _on_song_selection_changed(self) -> None:
        self._refresh_assignment_panel()

    def _on_assignment_changed(self) -> None:
        self._refresh_assignment_panel()
        self._refresh_error_column_only()

    def _refresh_error_column_only(self) -> None:
        if not self._selected_setlist_id:
            return
        rows = list_setlist_items_with_song_meta(self.app_state.conn, self._selected_setlist_id)
        sl = next(s for s in list_setlists(self.app_state.conn) if s.id == self._selected_setlist_id)
        slots = list_layout_slots(self.app_state.conn, sl.band_layout_id) if sl.band_layout_id else []
        pids = [s.player_id for s in slots]
        bulk = list_player_instruments_bulk(self.app_state.conn, pids) if pids else {}
        for i, r in enumerate(rows):
            err = self._song_has_error(sl, r, bulk, slots)
            flag = self.songs_table.item(i, 0)
            if flag:
                flag.setText("\u26a0" if err else "")
                flag.setForeground(QColor("#ff4444") if err else QColor(COLOR_ON_SURFACE))
                f = QFont()
                if err:
                    f.setPointSize(f.pointSize() + 4)
                    f.setWeight(QFont.Weight.Bold)
                flag.setFont(f)

    def _refresh_assignment_panel(self) -> None:
        if not self._selected_setlist_id or not self._editor_enabled:
            self.assignment_panel.clear()
            return
        row = self.songs_table.currentRow()
        if row < 0:
            self.assignment_panel.clear()
            return
        rows = list_setlist_items_with_song_meta(self.app_state.conn, self._selected_setlist_id)
        logical_row = row
        if logical_row < 0 or logical_row >= len(rows):
            self.assignment_panel.clear()
            return
        r = rows[logical_row]
        sl = next(s for s in list_setlists(self.app_state.conn) if s.id == self._selected_setlist_id)
        song_layout_id = r.item.song_layout_id
        created_layout = False
        if sl.band_layout_id and song_layout_id is None:
            song_layout_id = self._ensure_song_layout(r.item.song_id, sl.band_layout_id, r.item.id)
            created_layout = True
        self.assignment_panel.refresh(
            band_layout_id=sl.band_layout_id,
            setlist_item_id=r.item.id,
            song_layout_id=song_layout_id,
            parts_json=r.parts_json,
        )
        if created_layout:
            self._refresh_error_column_only()

    def _ensure_song_layout(self, song_id: int, band_layout_id: int, setlist_item_id: int) -> int | None:
        """Create song layout for this band if missing, update setlist item, return layout id."""
        layouts = list_song_layouts_for_song_and_band(self.app_state.conn, song_id, band_layout_id)
        if layouts:
            layout_id = layouts[0].id
        else:
            layout_id = add_song_layout(self.app_state.conn, song_id, band_layout_id, "Default")
            row = self.app_state.conn.execute(
                "SELECT band_id FROM BandLayout WHERE id = ?", (band_layout_id,)
            ).fetchone()
            if row:
                for player_id in list_band_members(self.app_state.conn, row[0]):
                    set_song_layout_assignment(self.app_state.conn, layout_id, player_id, None)
        update_setlist_item(self.app_state.conn, setlist_item_id, song_layout_id=layout_id)
        return layout_id

    def _add_setlist(self) -> None:
        bands = list_setlists(self.app_state.conn)
        n = sum(1 for b in bands if b.name.startswith("New setlist"))
        name = f"New setlist {n + 1}"
        add_setlist(self.app_state.conn, name)
        self._refresh_setlist_names()
        for i in range(self.setlist_list.count()):
            if self.setlist_list.item(i).text() == name:
                self.setlist_list.setCurrentRow(i)
                break

    def _save_setlist(self) -> None:
        if not self._selected_setlist_id:
            return
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Save", "Name cannot be empty.")
            return
        bl_id = self.band_layout_combo.currentData()
        notes = self.notes_edit.toPlainText().strip() or None
        d = self.set_date_edit.date()
        set_date = f"{d.year():04d}-{d.month():02d}-{d.day():02d}"
        t = self.set_time_edit.time()
        set_time = f"{t.hour():02d}:{t.minute():02d}"
        td = self.target_duration_edit.time()
        target_dur = (td.hour() * 3600 + td.minute() * 60) if (td.hour() or td.minute()) else None
        update_setlist(
            self.app_state.conn,
            self._selected_setlist_id,
            name=name,
            band_layout_id=bl_id,
            locked=self.locked_check.isChecked(),
            default_change_duration_seconds=self.default_duration_spin.value() or None,
            notes=notes,
            set_date=set_date,
            set_time=set_time,
            target_duration_seconds=target_dur,
        )
        self._loaded_name = name
        self._loaded_notes = notes or ""
        self._loaded_band_layout_id = bl_id
        self._loaded_locked = self.locked_check.isChecked()
        self._loaded_default_dur = self.default_duration_spin.value() or None
        self._loaded_set_date = set_date
        self._loaded_set_time = set_time
        self._loaded_target_dur = target_dur
        self._refresh_setlist_names()

    def has_unsaved_changes(self) -> bool:
        if not self._editor_enabled or self._selected_setlist_id is None:
            return False
        name = self.name_edit.text().strip()
        notes = self.notes_edit.toPlainText().strip() or ""
        bl = self.band_layout_combo.currentData()
        d = self.set_date_edit.date()
        set_date = f"{d.year():04d}-{d.month():02d}-{d.day():02d}"
        t = self.set_time_edit.time()
        set_time = f"{t.hour():02d}:{t.minute():02d}"
        td = self.target_duration_edit.time()
        target_dur = (td.hour() * 3600 + td.minute() * 60) if (td.hour() or td.minute()) else None
        if (
            name != self._loaded_name
            or notes != self._loaded_notes
            or bl != self._loaded_band_layout_id
            or self.locked_check.isChecked() != self._loaded_locked
            or (self.default_duration_spin.value() or None) != self._loaded_default_dur
            or set_date != self._loaded_set_date
            or set_time != self._loaded_set_time
            or target_dur != self._loaded_target_dur
        ):
            return True
        return False

    def _delete_selected_setlist(self) -> None:
        if not self._selected_setlist_id:
            return
        s = next(x for x in list_setlists(self.app_state.conn) if x.id == self._selected_setlist_id)
        if (
            QMessageBox.question(
                self,
                "Confirm",
                f"Delete setlist '{s.name}'?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            == QMessageBox.StandardButton.Yes
        ):
            delete_setlist(self.app_state.conn, s.id)
            self._selected_setlist_id = None
            self._refresh_setlist_names()
            self._set_editor_enabled(False)

    def _add_item(self) -> None:
        if not self._selected_setlist_id:
            return
        songs = list_library_songs(self.app_state.conn, limit=500)
        if not songs:
            QMessageBox.information(self, "Info", "No songs in library. Scan library first.")
            return
        titles = [r.title for r in songs]
        title, ok = QInputDialog.getItem(self, "Add song", "Song:", titles, 0, False)
        if not ok or not title:
            return
        song_id = next(r.song_id for r in songs if r.title == title)
        items = list_setlist_items_with_song_meta(self.app_state.conn, self._selected_setlist_id)
        position = len(items)
        new_id = add_setlist_item(
            self.app_state.conn,
            self._selected_setlist_id,
            song_id,
            position,
            song_layout_id=None,
        )
        self._refresh_songs_table(select_item_id=new_id)

    def _remove_item(self, item) -> None:
        remove_setlist_item(self.app_state.conn, item.id)
        self._refresh_songs_table()

    def _on_songs_header_section_resized(self, logical_index: int, old_size: int, new_size: int) -> None:
        self._songs_header_save_timer.start(150)

    def _save_songs_table_header_state(self) -> None:
        hh = self.songs_table.horizontalHeader()
        sizes = [hh.sectionSize(i) for i in range(hh.count())]
        set_setlists_songs_table_header_state(sizes)

    def _save_setlists_state(self) -> None:
        """Persist splitter positions and table column widths. Called from main window on close."""
        self._save_songs_table_header_state()
        set_setlists_top_split_state(self.top_split.sizes())

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._refresh_setlist_names()
        if not self._splitter_restored:
            self._splitter_restored = True
            saved = get_setlists_splitter_state()
            if saved:
                self.setlists_splitter.setSizes(saved)
        if not self._editor_splitter_restored:
            self._editor_splitter_restored = True
            saved = get_setlists_editor_splitter_state()
            if saved:
                self.editor_splitter.setSizes(saved)
        if not self._top_split_restored:
            self._top_split_restored = True
            saved = get_setlists_top_split_state()
            if saved:
                self.top_split.setSizes(saved)
        if not self._songs_table_header_restored:
            self._songs_table_header_restored = True
            saved = get_setlists_songs_table_header_state()
            if saved:
                hh = self.songs_table.horizontalHeader()
                for i, w in enumerate(saved):
                    if i < hh.count():
                        hh.resizeSection(i, w)
