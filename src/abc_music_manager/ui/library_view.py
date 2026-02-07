"""
Library view: filterable table of songs, opens Song Detail on selection.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTableView,
    QLineEdit,
    QLabel,
    QComboBox,
    QSpinBox,
    QPushButton,
    QAbstractItemView,
    QHeaderView,
    QMessageBox,
    QMenu,
)
from PySide6.QtCore import Qt, QAbstractTableModel, QModelIndex
from PySide6.QtGui import QColor, QAction

from ..services.app_state import AppState
from ..db import list_library_songs, get_status_list, LibrarySongRow
from ..db.setlist_repo import list_setlists, add_setlist_item, list_setlist_items
from ..db.song_layout_repo import list_song_layouts_for_song_and_band


def _format_duration(sec: Optional[int]) -> str:
    if sec is None:
        return "—"
    m, s = divmod(sec, 60)
    return f"{m}:{s:02d}"


def _format_last_played(iso: Optional[str]) -> str:
    if not iso:
        return "—"
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        delta = now - dt
        if delta.days > 365:
            return f"{delta.days // 365}y ago"
        if delta.days > 30:
            return f"{delta.days // 30}mo ago"
        if delta.days > 0:
            return f"{delta.days}d ago"
        if delta.seconds >= 3600:
            return f"{delta.seconds // 3600}h ago"
        if delta.seconds >= 60:
            return f"{delta.seconds // 60}m ago"
        return "Just now"
    except Exception:
        return iso or "—"


class LibraryTableModel(QAbstractTableModel):
    """Table model for library songs. Refreshes from list_library_songs with current filters."""

    COLUMNS = [
        "Title", "Composer(s)", "Transcriber", "Duration", "Parts",
        "Last played", "Plays", "Rating", "Status", "In set", "Notes", "Lyrics",
    ]

    def __init__(self, conn, parent=None) -> None:
        super().__init__(parent)
        self._conn = conn
        self._rows: list[LibrarySongRow] = []
        self._filter_title: str = ""
        self._filter_composer: str = ""
        self._filter_transcriber: str = ""
        self._filter_duration_min: Optional[int] = None
        self._filter_duration_max: Optional[int] = None
        self._filter_rating_min: Optional[int] = None
        self._filter_rating_max: Optional[int] = None
        self._filter_status_ids: Optional[list[int]] = None
        self._filter_part_count_min: Optional[int] = None
        self._filter_part_count_max: Optional[int] = None
        self._filter_plays_days: Optional[int] = None

    def set_filters(
        self,
        title: str = "",
        composer: str = "",
        transcriber: str = "",
        duration_min: Optional[int] = None,
        duration_max: Optional[int] = None,
        rating_min: Optional[int] = None,
        rating_max: Optional[int] = None,
        status_ids: Optional[list[int]] = None,
        part_count_min: Optional[int] = None,
        part_count_max: Optional[int] = None,
        plays_days: Optional[int] = None,
    ) -> None:
        self._filter_title = (title or "").strip()
        self._filter_composer = (composer or "").strip()
        self._filter_transcriber = (transcriber or "").strip()
        self._filter_duration_min = duration_min
        self._filter_duration_max = duration_max
        self._filter_rating_min = rating_min
        self._filter_rating_max = rating_max
        self._filter_status_ids = status_ids
        self._filter_part_count_min = part_count_min
        self._filter_part_count_max = part_count_max
        self._filter_plays_days = plays_days
        self.refresh()

    def refresh(self) -> None:
        self.beginResetModel()
        self._rows = list_library_songs(
            self._conn,
            title_substring=self._filter_title or None,
            composer_substring=self._filter_composer or None,
            transcriber_substring=self._filter_transcriber or None,
            duration_min_sec=self._filter_duration_min,
            duration_max_sec=self._filter_duration_max,
            rating_min=self._filter_rating_min,
            rating_max=self._filter_rating_max,
            status_ids=self._filter_status_ids,
            part_count_min=self._filter_part_count_min,
            part_count_max=self._filter_part_count_max,
            plays_in_last_n_days=self._filter_plays_days,
            limit=2000,
        )
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self._rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self.COLUMNS)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or index.row() >= len(self._rows):
            return None
        row = self._rows[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            c = index.column()
            if c == 0:
                return row.title
            if c == 1:
                return row.composers
            if c == 2:
                return row.transcriber or "—"
            if c == 3:
                return _format_duration(row.duration_seconds)
            if c == 4:
                return str(row.part_count)
            if c == 5:
                return _format_last_played(row.last_played_at)
            if c == 6:
                return str(row.total_plays)
            if c == 7:
                return str(row.rating) if row.rating is not None else "—"
            if c == 8:
                return row.status_name or "—"
            if c == 9:
                return "Yes" if row.in_upcoming_set else ""
            if c == 10:
                return "•" if (row.notes and row.notes.strip()) else ""
            if c == 11:
                return "•" if (row.lyrics and row.lyrics.strip()) else ""
        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole and 0 <= section < len(self.COLUMNS):
            return self.COLUMNS[section]
        return None

    def song_id_at(self, row: int) -> Optional[int]:
        if 0 <= row < len(self._rows):
            return self._rows[row].song_id
        return None


class LibraryView(QWidget):
    """Library table with filter bar and open Song Detail on double-click."""

    def __init__(self, app_state: AppState, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.app_state = app_state
        layout = QVBoxLayout(self)

        # Filter row
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("Title:"))
        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("Filter by title")
        self.title_edit.setMaximumWidth(160)
        filter_layout.addWidget(self.title_edit)
        filter_layout.addWidget(QLabel("Composer:"))
        self.composer_edit = QLineEdit()
        self.composer_edit.setPlaceholderText("Filter")
        self.composer_edit.setMaximumWidth(140)
        filter_layout.addWidget(self.composer_edit)
        filter_layout.addWidget(QLabel("Status:"))
        self.status_combo = QComboBox()
        self.status_combo.setMaximumWidth(120)
        self.status_combo.addItem("(all)", None)
        filter_layout.addWidget(self.status_combo)
        filter_layout.addWidget(QLabel("Plays in last (days):"))
        self.plays_days_spin = QSpinBox()
        self.plays_days_spin.setRange(0, 365)
        self.plays_days_spin.setSpecialValueText("—")
        self.plays_days_spin.setMaximumWidth(60)
        filter_layout.addWidget(self.plays_days_spin)
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self._apply_filters)
        filter_layout.addWidget(self.refresh_btn)
        filter_layout.addStretch()
        layout.addLayout(filter_layout)

        self.model = LibraryTableModel(app_state.conn)
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.setAlternatingRowColors(True)
        self.table.doubleClicked.connect(self._on_double_click)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_context_menu)
        layout.addWidget(self.table)

        self._load_status_combo()
        self.model.refresh()

    def _load_status_combo(self) -> None:
        from ..db import get_status_list
        self.status_combo.clear()
        self.status_combo.addItem("(all)", None)
        for sid, name in get_status_list(self.app_state.conn):
            self.status_combo.addItem(name, sid)

    def _apply_filters(self) -> None:
        status_data = self.status_combo.currentData()
        status_ids = [status_data] if status_data is not None and status_data != -1 else None
        plays_days = self.plays_days_spin.value()
        if plays_days <= 0:
            plays_days = None
        self.model.set_filters(
            title=self.title_edit.text(),
            composer=self.composer_edit.text(),
            status_ids=status_ids,
            plays_days=plays_days,
        )

    def _on_double_click(self, index: QModelIndex) -> None:
        song_id = self.model.song_id_at(index.row())
        if song_id is not None:
            self._open_song_detail(song_id)

    def _on_context_menu(self, pos) -> None:
        index = self.table.indexAt(pos)
        song_id = self.model.song_id_at(index.row()) if index.isValid() else None
        if song_id is None:
            return
        menu = QMenu(self)
        add_to_set = menu.addMenu("Add to Set")
        unlocked = [s for s in list_setlists(self.app_state.conn) if not s.locked]
        for s in unlocked:
            act = add_to_set.addAction(s.name)
            act.triggered.connect(lambda checked=False, setlist_id=s.id, sid=song_id: self._add_song_to_set(setlist_id, sid))
        if not unlocked:
            add_to_set.setEnabled(False)
        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _add_song_to_set(self, setlist_id: int, song_id: int) -> None:
        items = list_setlist_items(self.app_state.conn, setlist_id)
        position = len(items)
        setlist = next(s for s in list_setlists(self.app_state.conn) if s.id == setlist_id)
        song_layout_id = None
        if setlist.band_layout_id:
            layouts = list_song_layouts_for_song_and_band(self.app_state.conn, song_id, setlist.band_layout_id)
            if layouts:
                song_layout_id = layouts[0].id
        add_setlist_item(self.app_state.conn, setlist_id, song_id, position, song_layout_id=song_layout_id)
        QMessageBox.information(self, "Added", "Song added to setlist.")

    def _open_song_detail(self, song_id: int) -> None:
        from .song_detail import SongDetailDialog
        dlg = SongDetailDialog(self.app_state, song_id, self)
        dlg.exec()
        self.model.refresh()

    def refresh(self) -> None:
        self.model.refresh()
