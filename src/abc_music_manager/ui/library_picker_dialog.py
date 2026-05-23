"""
Dialog for browsing the library and adding songs to a setlist.
"""

from __future__ import annotations

from datetime import timezone
from typing import Callable, Optional

from PySide6.QtCore import (
    QAbstractTableModel,
    QEvent,
    QModelIndex,
    QObject,
    QRect,
    Qt,
    QTime,
    QTimer,
    Signal,
)
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDateTimeEdit,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTableView,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from ..db import LibrarySongRow, list_library_songs, list_unique_transcribers
from ..db.setlist_repo import add_setlist_item, list_setlist_items, list_setlists
from ..db.song_layout_repo import list_song_layouts_for_song_and_band
from ..db.status_repo import list_statuses
from ..services.app_state import AppState
from ..services.preferences import get_default_filters
from .library_view import (
    LAST_PLAYED_TIME_OPTS,
    LibrarySortProxy,
    RatingComboBox,
    RatingComboDelegate,
    RowDataRole,
    SortRole,
    StatusColorRole,
    _PopupHideFilter,
    _format_duration,
    _format_last_played,
    _index_for_seconds_ago,
    _rating_label,
    _seconds_to_time_edit,
    _status_chip_style,
    _time_edit_to_seconds,
    _transcriber_chip_style,
)
from .theme import COLOR_OUTLINE_VARIANT, COLOR_TEXT_SECONDARY, STATUS_CIRCLE_DIAMETER


class LibraryPickerTableModel(QAbstractTableModel):
    """Slim library table for the setlist song picker."""

    COLUMNS = [
        "",
        "Title",
        "Composer(s)",
        "Duration",
        "Parts",
        "Last played",
        "Status",
        "Rating",
        "Transcriber",
    ]

    _SORTABLE_COLUMNS = (1, 2, 3, 4, 5, 6, 7, 8)

    def __init__(self, conn, parent=None) -> None:
        super().__init__(parent)
        self._conn = conn
        self._rows: list[LibrarySongRow] = []
        self._filter_title_composer: str = ""
        self._filter_transcriber_in: Optional[list[str]] = None
        self._filter_duration_min: Optional[int] = None
        self._filter_duration_max: Optional[int] = None
        self._filter_rating_min: Optional[int] = None
        self._filter_rating_max: Optional[int] = None
        self._filter_status_ids: Optional[list[int]] = None
        self._filter_part_count_min: Optional[int] = None
        self._filter_part_count_max: Optional[int] = None
        self._filter_last_played_never: bool = False
        self._filter_last_played_min_seconds_ago: Optional[int] = None
        self._filter_last_played_max_seconds_ago: Optional[int] = None
        self._filter_last_played_after_iso: Optional[str] = None
        self._filter_last_played_before_iso: Optional[str] = None
        self._filter_in_set: Optional[str] = None
        self._default_status_name: Optional[str] = None
        self._default_status_color: Optional[str] = None

    def set_filters(
        self,
        title_or_composer: str = "",
        transcriber_in: Optional[list[str]] = None,
        duration_min: Optional[int] = None,
        duration_max: Optional[int] = None,
        rating_min: Optional[int] = None,
        rating_max: Optional[int] = None,
        status_ids: Optional[list[int]] = None,
        part_count_min: Optional[int] = None,
        part_count_max: Optional[int] = None,
        last_played_never: bool = False,
        last_played_min_seconds_ago: Optional[int] = None,
        last_played_max_seconds_ago: Optional[int] = None,
        last_played_after_iso: Optional[str] = None,
        last_played_before_iso: Optional[str] = None,
        in_set: Optional[str] = None,
    ) -> None:
        self._filter_title_composer = (title_or_composer or "").strip()
        self._filter_transcriber_in = transcriber_in if transcriber_in else None
        self._filter_duration_min = duration_min
        self._filter_duration_max = duration_max
        self._filter_rating_min = rating_min
        self._filter_rating_max = rating_max
        self._filter_status_ids = status_ids
        self._filter_part_count_min = part_count_min
        self._filter_part_count_max = part_count_max
        self._filter_last_played_never = last_played_never
        self._filter_last_played_min_seconds_ago = last_played_min_seconds_ago
        self._filter_last_played_max_seconds_ago = last_played_max_seconds_ago
        self._filter_last_played_after_iso = last_played_after_iso
        self._filter_last_played_before_iso = last_played_before_iso
        self._filter_in_set = in_set if in_set in ("yes", "no") else None
        self.refresh()

    def _resolve_default_status(self) -> None:
        from ..db.status_repo import get_effective_default_status_id

        default_id = get_effective_default_status_id(self._conn)
        self._default_status_name = None
        self._default_status_color = None
        if default_id:
            for s in list_statuses(self._conn):
                if s.id == default_id:
                    self._default_status_name = s.name
                    self._default_status_color = s.color
                    break

    def refresh(self) -> None:
        self._resolve_default_status()
        self.beginResetModel()
        self._rows = list_library_songs(
            self._conn,
            title_or_composer_substring=self._filter_title_composer or None,
            transcriber_in=self._filter_transcriber_in,
            duration_min_sec=self._filter_duration_min,
            duration_max_sec=self._filter_duration_max,
            rating_min=self._filter_rating_min,
            rating_max=self._filter_rating_max,
            status_ids=self._filter_status_ids,
            part_count_min=self._filter_part_count_min,
            part_count_max=self._filter_part_count_max,
            last_played_never=self._filter_last_played_never,
            last_played_min_seconds_ago=self._filter_last_played_min_seconds_ago,
            last_played_max_seconds_ago=self._filter_last_played_max_seconds_ago,
            last_played_after_iso=self._filter_last_played_after_iso,
            last_played_before_iso=self._filter_last_played_before_iso,
            in_set_filter=self._filter_in_set,
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
        c = index.column()
        if role == RowDataRole:
            return row
        if role == Qt.ItemDataRole.DisplayRole:
            if c == 0:
                return None
            if c == 1:
                return row.title
            if c == 2:
                return row.composers
            if c == 3:
                return _format_duration(row.duration_seconds) or "—"
            if c == 4:
                return str(row.part_count)
            if c == 5:
                return None
            if c == 6:
                return row.status_name or self._default_status_name or "—"
            if c == 7:
                return None
            if c == 8:
                return row.transcriber or "—"
        if role == SortRole:
            if c == 3:
                return row.duration_seconds if row.duration_seconds is not None else -1
            if c == 4:
                return row.part_count
            if c == 5:
                return row.last_played_at or ""
            if c == 7:
                return row.rating if row.rating is not None else -1
        if role == StatusColorRole and c == 6:
            return row.status_color or self._default_status_color
        if role == Qt.ItemDataRole.ToolTipRole and c == 0:
            return "Add to setlist"
        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole and 0 <= section < len(self.COLUMNS):
            return self.COLUMNS[section]
        return None

    def song_id_at(self, row: int) -> Optional[int]:
        if 0 <= row < len(self._rows):
            return self._rows[row].song_id
        return None

    def row_at(self, row: int) -> Optional[LibrarySongRow]:
        if 0 <= row < len(self._rows):
            return self._rows[row]
        return None


class LibraryPickerDelegate(QStyledItemDelegate):
    """Paints add button, last played, rating, and status columns."""

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        option.state &= ~(QStyle.StateFlag.State_MouseOver | QStyle.StateFlag.State_HasFocus)
        col = index.column()
        row_data = index.data(RowDataRole)
        if col == 0:
            self._paint_add_button(painter, option)
            return
        if col == 5 and row_data:
            rect = option.rect.adjusted(2, 1, -2, -1)
            painter.drawText(
                rect,
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                _format_last_played(row_data.last_played_at),
            )
            return
        if col == 6 and row_data:
            self._paint_status(painter, option, index)
            return
        if col == 7 and row_data:
            self._paint_rating(painter, option, row_data)
            return
        super().paint(painter, option, index)

    def _paint_add_button(self, painter: QPainter, option: QStyleOptionViewItem) -> None:
        rect = option.rect.adjusted(2, 1, -2, -1)
        btn_w, btn_h = 28, 26
        line_h = option.fontMetrics.lineSpacing()
        btn_y = rect.y() + (2 * line_h - btn_h) // 2
        btn_x = rect.x() + (rect.width() - btn_w) // 2
        btn_rect = QRect(btn_x, btn_y, btn_w, btn_h)
        painter.setPen(QPen(option.palette.color(option.palette.currentColorGroup(), option.palette.ColorRole.Mid)))
        painter.setBrush(QBrush(option.palette.button()))
        painter.drawRoundedRect(btn_rect, 4, 4)
        painter.setPen(QPen(option.palette.color(option.palette.currentColorGroup(), option.palette.ColorRole.ButtonText)))
        bold_font = QFont(option.font)
        bold_font.setWeight(QFont.Weight.ExtraBold)
        painter.setFont(bold_font)
        painter.drawText(btn_rect, Qt.AlignmentFlag.AlignCenter, "+")

    def _paint_rating(self, painter: QPainter, option: QStyleOptionViewItem, row: LibrarySongRow) -> None:
        rect = option.rect.adjusted(2, 1, -2, -1)
        star_x = rect.x()
        cy = rect.center().y()
        line_h = option.fontMetrics.lineSpacing()
        star_y = cy - line_h // 2
        rating = row.rating if row.rating is not None else 0
        filled = "\u2605"
        empty = "\u2606"
        for i in range(1, 6):
            char = filled if i <= rating else empty
            color = (
                QColor(255, 200, 0)
                if i <= rating
                else option.palette.color(option.palette.currentColorGroup(), option.palette.ColorRole.Text)
            )
            painter.setPen(QPen(color))
            painter.drawText(star_x + (i - 1) * 14, star_y, 14, line_h, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, char)

    def _paint_status(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        rect = option.rect.adjusted(2, 0, -2, 0)
        name = index.data(Qt.ItemDataRole.DisplayRole) or "—"
        color = index.data(StatusColorRole)
        try:
            qcolor = QColor(color) if color else option.palette.text().color()
        except Exception:
            qcolor = option.palette.text().color()
        painter.setBrush(QBrush(qcolor))
        painter.setPen(Qt.PenStyle.NoPen)
        cy = rect.center().y()
        r = STATUS_CIRCLE_DIAMETER // 2
        painter.drawEllipse(rect.x(), cy - r, STATUS_CIRCLE_DIAMETER, STATUS_CIRCLE_DIAMETER)
        painter.setPen(QPen(option.palette.text().color()))
        painter.drawText(
            rect.adjusted(STATUS_CIRCLE_DIAMETER + 4, 0, 0, 0),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            name,
        )


class LibraryPickerDialog(QDialog):
    """Browse and filter the library; add songs to a setlist without closing."""

    songAdded = Signal(int)

    def __init__(self, app_state: AppState, setlist_id: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.app_state = app_state
        self._setlist_id = setlist_id
        self._sort_column = 1
        self._sort_order = Qt.SortOrder.AscendingOrder
        self._selected_status_ids: list[int] = []
        self._status_popup: QWidget | None = None
        self._status_just_closed = False
        self._status_just_closed_timer: QTimer | None = None
        self._selected_transcribers: list[str] = []
        self._transcriber_popup: QWidget | None = None
        self._transcriber_just_closed = False
        self._transcriber_just_closed_timer: QTimer | None = None

        setlist = next((s for s in list_setlists(app_state.conn) if s.id == setlist_id), None)
        title = f"Add songs — {setlist.name}" if setlist else "Add songs"
        self.setWindowTitle(title)
        self.resize(980, 620)

        layout = QVBoxLayout(self)
        layout.addWidget(self._build_filter_widget())

        self.model = LibraryPickerTableModel(app_state.conn, self)
        self.proxy = LibrarySortProxy(self)
        self.proxy.setSourceModel(self.model)
        self.proxy.setSortCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.proxy.sort(self._sort_column, self._sort_order)

        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.table.setItemDelegate(LibraryPickerDelegate(self.table))
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(False)
        hh = self.table.horizontalHeader()
        hh.setMinimumSectionSize(24)
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        hh.resizeSection(0, 40)
        for i in range(1, hh.count()):
            hh.setSectionResizeMode(i, QHeaderView.ResizeMode.Interactive)
        hh.setSectionsClickable(True)
        hh.setSortIndicatorShown(True)
        hh.sectionClicked.connect(self._on_header_clicked)
        fm = self.table.fontMetrics()
        self.table.verticalHeader().setDefaultSectionSize(2 * fm.lineSpacing() + 10)
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self.table.viewport().installEventFilter(self)
        layout.addWidget(self.table)

        hint = QLabel("Click + on a row to add that song to the set. The dialog stays open so you can add more.")
        hint.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY};")
        layout.addWidget(hint)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        close_btn = buttons.button(QDialogButtonBox.StandardButton.Close)
        if close_btn is not None:
            close_btn.setText("Done")
        layout.addWidget(buttons)

        self._apply_default_filters()

    def _build_filter_widget(self) -> QWidget:
        filter_widget = QWidget()
        filter_layout = QVBoxLayout(filter_widget)
        filter_layout.setContentsMargins(0, 0, 0, 4)

        main_row = QHBoxLayout()
        main_row.addWidget(QLabel("Title / Composer:"))
        self.title_composer_edit = QLineEdit()
        self.title_composer_edit.setPlaceholderText("Filter by title or composer")
        self.title_composer_edit.setClearButtonEnabled(True)
        self.title_composer_edit.setMaximumWidth(220)
        self.title_composer_edit.textChanged.connect(self._apply_filters)
        main_row.addWidget(self.title_composer_edit)
        main_row.addWidget(QLabel("Status:"))
        self.status_btn = QPushButton("All statuses")
        self.status_btn.setObjectName("status_filter_btn")
        self.status_btn.setCheckable(True)
        self.status_btn.clicked.connect(self._on_status_filter_clicked)
        main_row.addWidget(self.status_btn)
        main_row.addWidget(QLabel("In set:"))
        self.in_set_combo = QComboBox()
        self.in_set_combo.addItem("Either", None)
        self.in_set_combo.addItem("Yes", "yes")
        self.in_set_combo.addItem("No", "no")
        self.in_set_combo.currentIndexChanged.connect(self._apply_filters)
        main_row.addWidget(self.in_set_combo)
        main_row.addWidget(QLabel("Rating:"))
        self.rating_from_combo = RatingComboBox()
        self.rating_from_combo.setItemDelegate(RatingComboDelegate(self.rating_from_combo))
        for i in range(6):
            self.rating_from_combo.addItem(_rating_label(i), i)
        self.rating_from_combo.currentIndexChanged.connect(self._on_rating_from_changed)
        main_row.addWidget(self.rating_from_combo)
        main_row.addWidget(QLabel("to"))
        self.rating_to_combo = RatingComboBox()
        self.rating_to_combo.setItemDelegate(RatingComboDelegate(self.rating_to_combo))
        for i in range(6):
            self.rating_to_combo.addItem(_rating_label(i), i)
        self.rating_to_combo.setCurrentIndex(5)
        self.rating_to_combo.currentIndexChanged.connect(self._on_rating_to_changed)
        main_row.addWidget(self.rating_to_combo)
        self.more_filters_btn = QPushButton("More Filters")
        self.more_filters_btn.setCheckable(True)
        self.more_filters_btn.toggled.connect(self._on_more_filters_toggled)
        main_row.addWidget(self.more_filters_btn)
        reset_btn = QPushButton("Reset Filters")
        reset_btn.clicked.connect(self._reset_filters)
        main_row.addWidget(reset_btn)
        clear_btn = QPushButton("Clear Filters")
        clear_btn.clicked.connect(self._clear_filters)
        main_row.addWidget(clear_btn)
        main_row.addStretch()
        filter_layout.addLayout(main_row)

        self.more_filters_panel = QWidget()
        more_layout = QVBoxLayout(self.more_filters_panel)
        more_layout.setContentsMargins(0, 8, 0, 4)
        more_row1 = QHBoxLayout()
        more_row1.addWidget(QLabel("Duration:"))
        self.duration_min_none = QCheckBox("None")
        self.duration_min_none.setChecked(True)
        self.duration_min_none.toggled.connect(self._on_duration_none_toggled)
        more_row1.addWidget(self.duration_min_none)
        self.duration_min_edit = QTimeEdit()
        self.duration_min_edit.setDisplayFormat("m:ss")
        self.duration_min_edit.setTime(QTime(0, 0, 0))
        self.duration_min_edit.setEnabled(False)
        self.duration_min_edit.timeChanged.connect(self._on_duration_min_changed)
        more_row1.addWidget(self.duration_min_edit)
        more_row1.addWidget(QLabel("to"))
        self.duration_max_none = QCheckBox("None")
        self.duration_max_none.setChecked(True)
        self.duration_max_none.toggled.connect(self._on_duration_none_toggled)
        more_row1.addWidget(self.duration_max_none)
        self.duration_max_edit = QTimeEdit()
        self.duration_max_edit.setDisplayFormat("m:ss")
        self.duration_max_edit.setTime(QTime(0, 20, 0))
        self.duration_max_edit.setEnabled(False)
        self.duration_max_edit.timeChanged.connect(self._on_duration_max_changed)
        more_row1.addWidget(self.duration_max_edit)
        more_row1.addSpacing(16)
        more_row1.addWidget(QLabel("Last played:"))
        self.last_played_mode_combo = QComboBox()
        self.last_played_mode_combo.addItem("Time range", "time")
        self.last_played_mode_combo.addItem("Date range", "date")
        self.last_played_mode_combo.currentIndexChanged.connect(self._on_last_played_mode_changed)
        more_row1.addWidget(self.last_played_mode_combo)
        self.last_played_from_combo = QComboBox()
        for label, sec in LAST_PLAYED_TIME_OPTS:
            self.last_played_from_combo.addItem(label, sec)
        self.last_played_from_combo.currentIndexChanged.connect(self._on_last_played_from_time_changed)
        more_row1.addWidget(self.last_played_from_combo)
        self.last_played_to_combo = QComboBox()
        for label, sec in LAST_PLAYED_TIME_OPTS:
            self.last_played_to_combo.addItem(label, sec)
        self.last_played_to_combo.setCurrentIndex(self.last_played_to_combo.count() - 1)
        self.last_played_to_combo.currentIndexChanged.connect(self._on_last_played_to_time_changed)
        more_row1.addWidget(self.last_played_to_combo)
        self.last_played_from_dt = QDateTimeEdit()
        self.last_played_from_dt.setCalendarPopup(True)
        self.last_played_from_dt.setDisplayFormat("yyyy-MM-dd hh:mm")
        self.last_played_from_dt.setVisible(False)
        self.last_played_from_dt.dateTimeChanged.connect(self._on_last_played_from_date_changed)
        more_row1.addWidget(self.last_played_from_dt)
        self.last_played_to_dt = QDateTimeEdit()
        self.last_played_to_dt.setCalendarPopup(True)
        self.last_played_to_dt.setDisplayFormat("yyyy-MM-dd hh:mm")
        self.last_played_to_dt.setVisible(False)
        self.last_played_to_dt.dateTimeChanged.connect(self._on_last_played_to_date_changed)
        more_row1.addWidget(self.last_played_to_dt)
        more_row1.addStretch()
        more_layout.addLayout(more_row1)

        more_row2 = QHBoxLayout()
        more_row2.addWidget(QLabel("Parts:"))
        self.parts_min_combo = QComboBox()
        for n in range(1, 25):
            self.parts_min_combo.addItem(str(n), n)
        self.parts_min_combo.currentIndexChanged.connect(self._on_parts_min_changed)
        more_row2.addWidget(self.parts_min_combo)
        more_row2.addWidget(QLabel("to"))
        self.parts_max_combo = QComboBox()
        for n in range(1, 25):
            self.parts_max_combo.addItem(str(n), n)
        self.parts_max_combo.setCurrentIndex(23)
        self.parts_max_combo.currentIndexChanged.connect(self._on_parts_max_changed)
        more_row2.addWidget(self.parts_max_combo)
        more_row2.addSpacing(16)
        more_row2.addWidget(QLabel("Transcriber:"))
        self.transcriber_btn = QPushButton("All transcribers")
        self.transcriber_btn.setCheckable(True)
        self.transcriber_btn.clicked.connect(self._on_transcriber_filter_clicked)
        more_row2.addWidget(self.transcriber_btn)
        more_row2.addStretch()
        more_layout.addLayout(more_row2)
        self.more_filters_panel.setVisible(False)
        filter_layout.addWidget(self.more_filters_panel)
        return filter_widget

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if obj is self.table.viewport() and event.type() == QEvent.Type.MouseButtonPress:
            pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
            index = self.table.indexAt(pos)
            if not index.isValid() or index.column() != 0:
                return False
            source_row = self.proxy.mapToSource(index).row()
            row_data = self.model.row_at(source_row)
            if not row_data:
                return False
            rect = self.table.visualRect(index)
            x = pos.x() - rect.x()
            y = pos.y() - rect.y()
            btn_w, btn_h = 28, 26
            line_h = self.table.fontMetrics().lineSpacing()
            btn_y = (2 * line_h - btn_h) // 2
            btn_x = (rect.width() - btn_w) // 2
            if btn_x <= x <= btn_x + btn_w and btn_y <= y <= btn_y + btn_h:
                self._add_song(row_data.song_id)
                return True
        return super().eventFilter(obj, event)

    def _add_song(self, song_id: int) -> None:
        items = list_setlist_items(self.app_state.conn, self._setlist_id)
        position = len(items)
        setlist = next(s for s in list_setlists(self.app_state.conn) if s.id == self._setlist_id)
        song_layout_id = None
        if setlist.band_layout_id:
            layouts = list_song_layouts_for_song_and_band(
                self.app_state.conn, song_id, setlist.band_layout_id
            )
            if layouts:
                song_layout_id = layouts[0].id
        add_setlist_item(
            self.app_state.conn,
            self._setlist_id,
            song_id,
            position,
            song_layout_id=song_layout_id,
        )
        self.songAdded.emit(song_id)
        self.model.refresh()
        self.table.horizontalHeader().setSortIndicator(self._sort_column, self._sort_order)
        self.proxy.sort(self._sort_column, self._sort_order)

    def _on_header_clicked(self, logical_index: int) -> None:
        if logical_index not in LibraryPickerTableModel._SORTABLE_COLUMNS:
            return
        if logical_index == self._sort_column:
            self._sort_order = (
                Qt.SortOrder.DescendingOrder
                if self._sort_order == Qt.SortOrder.AscendingOrder
                else Qt.SortOrder.AscendingOrder
            )
        else:
            self._sort_column = logical_index
            self._sort_order = Qt.SortOrder.AscendingOrder
        self.table.horizontalHeader().setSortIndicator(self._sort_column, self._sort_order)
        self.proxy.sort(self._sort_column, self._sort_order)

    def _apply_filters(self) -> None:
        title = self.title_composer_edit.text()
        status_ids = self._selected_status_ids if self._selected_status_ids else None
        in_set = self.in_set_combo.currentData()
        r_from = self.rating_from_combo.currentData()
        r_to = self.rating_to_combo.currentData()
        rating_min = None if (r_from == 0 and r_to == 5) else (r_from if r_from is not None else 0)
        rating_max = None if (r_from == 0 and r_to == 5) else (r_to if r_to is not None else 5)
        transcriber_in = self._selected_transcribers if self._selected_transcribers else None

        duration_min = None
        duration_max = None
        if not self.duration_min_none.isChecked():
            duration_min = _time_edit_to_seconds(self.duration_min_edit)
        if not self.duration_max_none.isChecked():
            duration_max = _time_edit_to_seconds(self.duration_max_edit)

        last_played_never = False
        last_played_min_sec = None
        last_played_max_sec = None
        last_played_after_iso = None
        last_played_before_iso = None
        if self.last_played_mode_combo.currentData() == "time":
            sec_from = self.last_played_from_combo.currentData()
            sec_to = self.last_played_to_combo.currentData()
            if sec_from is None and sec_to is None:
                last_played_never = True
            elif sec_from is not None or sec_to is not None:
                last_played_min_sec = sec_from
                last_played_max_sec = sec_to
        else:
            dt_from = self.last_played_from_dt.dateTime().toPython()
            dt_to = self.last_played_to_dt.dateTime().toPython()
            if dt_from.tzinfo is None:
                dt_from = dt_from.replace(tzinfo=timezone.utc)
            if dt_to.tzinfo is None:
                dt_to = dt_to.replace(tzinfo=timezone.utc)
            last_played_after_iso = dt_from.isoformat()
            last_played_before_iso = dt_to.isoformat()

        p_lo = self.parts_min_combo.currentData()
        p_hi = self.parts_max_combo.currentData()
        part_count_min = None if (p_lo == 1 and p_hi == 24) else (p_lo if p_lo is not None else 1)
        part_count_max = None if (p_lo == 1 and p_hi == 24) else (p_hi if p_hi is not None else 24)

        self.model.set_filters(
            title_or_composer=title,
            transcriber_in=transcriber_in,
            duration_min=duration_min,
            duration_max=duration_max,
            rating_min=rating_min,
            rating_max=rating_max,
            status_ids=status_ids,
            part_count_min=part_count_min,
            part_count_max=part_count_max,
            last_played_never=last_played_never,
            last_played_min_seconds_ago=last_played_min_sec,
            last_played_max_seconds_ago=last_played_max_sec,
            last_played_after_iso=last_played_after_iso,
            last_played_before_iso=last_played_before_iso,
            in_set=in_set,
        )
        self.table.horizontalHeader().setSortIndicator(self._sort_column, self._sort_order)
        self.proxy.sort(self._sort_column, self._sort_order)

    def _apply_filters_from_values(
        self,
        *,
        in_set: Optional[str],
        rating_from: int,
        rating_to: int,
        duration_min_none: bool,
        duration_max_none: bool,
        duration_min_sec: int,
        duration_max_sec: int,
        last_played_mode: str,
        last_played_from_seconds_ago: Optional[int],
        last_played_to_seconds_ago: Optional[int],
        last_played_from_iso: Optional[str],
        last_played_to_iso: Optional[str],
        parts_min: int,
        parts_max: int,
        status_ids: list[int],
    ) -> None:
        self.title_composer_edit.blockSignals(True)
        self.in_set_combo.blockSignals(True)
        self.rating_from_combo.blockSignals(True)
        self.rating_to_combo.blockSignals(True)
        self.duration_min_none.blockSignals(True)
        self.duration_max_none.blockSignals(True)
        self.duration_min_edit.blockSignals(True)
        self.duration_max_edit.blockSignals(True)
        self.last_played_mode_combo.blockSignals(True)
        self.last_played_from_combo.blockSignals(True)
        self.last_played_to_combo.blockSignals(True)
        self.last_played_from_dt.blockSignals(True)
        self.last_played_to_dt.blockSignals(True)
        self.parts_min_combo.blockSignals(True)
        self.parts_max_combo.blockSignals(True)

        self.title_composer_edit.clear()
        self._selected_status_ids = list(status_ids)
        self.status_btn.setText(
            "All statuses"
            if not self._selected_status_ids
            else ("1 status" if len(self._selected_status_ids) == 1 else f"{len(self._selected_status_ids)} statuses")
        )
        for i in range(self.in_set_combo.count()):
            if self.in_set_combo.itemData(i) == in_set:
                self.in_set_combo.setCurrentIndex(i)
                break
        self.rating_from_combo.setCurrentIndex(min(5, max(0, rating_from)))
        self.rating_to_combo.setCurrentIndex(min(5, max(0, rating_to)))
        self.duration_min_none.setChecked(duration_min_none)
        self.duration_max_none.setChecked(duration_max_none)
        self.duration_min_edit.setEnabled(not duration_min_none)
        self.duration_max_edit.setEnabled(not duration_max_none)
        _seconds_to_time_edit(duration_min_sec, self.duration_min_edit)
        _seconds_to_time_edit(duration_max_sec, self.duration_max_edit)
        if duration_max_none:
            self.duration_max_edit.setTime(QTime(0, 0, 0))
        self.last_played_mode_combo.setCurrentIndex(0 if last_played_mode == "time" else 1)
        self.last_played_from_combo.setVisible(last_played_mode == "time")
        self.last_played_to_combo.setVisible(last_played_mode == "time")
        self.last_played_from_dt.setVisible(last_played_mode == "date")
        self.last_played_to_dt.setVisible(last_played_mode == "date")
        self.last_played_from_combo.setCurrentIndex(_index_for_seconds_ago(last_played_from_seconds_ago))
        self.last_played_to_combo.setCurrentIndex(
            _index_for_seconds_ago(last_played_to_seconds_ago)
            if last_played_to_seconds_ago is not None
            else self.last_played_to_combo.count() - 1
        )
        self.parts_min_combo.setCurrentIndex(max(0, min(23, parts_min - 1)))
        self.parts_max_combo.setCurrentIndex(max(0, min(23, parts_max - 1)))
        self._selected_transcribers = []
        self.transcriber_btn.setText("All transcribers")

        self.title_composer_edit.blockSignals(False)
        self.in_set_combo.blockSignals(False)
        self.rating_from_combo.blockSignals(False)
        self.rating_to_combo.blockSignals(False)
        self.duration_min_none.blockSignals(False)
        self.duration_max_none.blockSignals(False)
        self.duration_min_edit.blockSignals(False)
        self.duration_max_edit.blockSignals(False)
        self.last_played_mode_combo.blockSignals(False)
        self.last_played_from_combo.blockSignals(False)
        self.last_played_to_combo.blockSignals(False)
        self.last_played_from_dt.blockSignals(False)
        self.last_played_to_dt.blockSignals(False)
        self.parts_min_combo.blockSignals(False)
        self.parts_max_combo.blockSignals(False)
        self._apply_filters()

    def _apply_default_filters(self) -> None:
        defaults = get_default_filters()
        self._apply_filters_from_values(
            in_set=defaults.get("in_set"),
            rating_from=int(defaults.get("rating_from", 0)),
            rating_to=int(defaults.get("rating_to", 5)),
            duration_min_none=bool(defaults.get("duration_min_none", True)),
            duration_max_none=bool(defaults.get("duration_max_none", True)),
            duration_min_sec=int(defaults.get("duration_min_sec", 0)),
            duration_max_sec=int(defaults.get("duration_max_sec", 1200)),
            last_played_mode=defaults.get("last_played_mode", "time") or "time",
            last_played_from_seconds_ago=defaults.get("last_played_from_seconds_ago", 0),
            last_played_to_seconds_ago=defaults.get("last_played_to_seconds_ago"),
            last_played_from_iso=defaults.get("last_played_from_iso"),
            last_played_to_iso=defaults.get("last_played_to_iso"),
            parts_min=int(defaults.get("parts_min", 1)),
            parts_max=int(defaults.get("parts_max", 24)),
            status_ids=list(defaults.get("status_ids") or []),
        )

    def _reset_filters(self) -> None:
        self._apply_default_filters()

    def _clear_filters(self) -> None:
        self._apply_filters_from_values(
            in_set=None,
            rating_from=0,
            rating_to=5,
            duration_min_none=True,
            duration_max_none=True,
            duration_min_sec=0,
            duration_max_sec=1200,
            last_played_mode="time",
            last_played_from_seconds_ago=0,
            last_played_to_seconds_ago=None,
            last_played_from_iso=None,
            last_played_to_iso=None,
            parts_min=1,
            parts_max=24,
            status_ids=[],
        )

    def _on_more_filters_toggled(self, checked: bool) -> None:
        self.more_filters_panel.setVisible(checked)

    def _on_duration_none_toggled(self) -> None:
        self.duration_min_edit.setEnabled(not self.duration_min_none.isChecked())
        self.duration_max_edit.setEnabled(not self.duration_max_none.isChecked())
        if self.duration_min_none.isChecked():
            self.duration_min_edit.setTime(QTime(0, 0, 0))
        if self.duration_max_none.isChecked():
            self.duration_max_edit.setTime(QTime(0, 0, 0))
        else:
            self.duration_max_edit.setTime(QTime(0, 20, 0))
        self._apply_filters()

    def _on_duration_min_changed(self) -> None:
        if self.duration_min_none.isChecked():
            return
        low = _time_edit_to_seconds(self.duration_min_edit)
        high = _time_edit_to_seconds(self.duration_max_edit) if not self.duration_max_none.isChecked() else None
        if high is not None and low > high:
            _seconds_to_time_edit(low, self.duration_max_edit)
        self._apply_filters()

    def _on_duration_max_changed(self) -> None:
        if self.duration_max_none.isChecked():
            return
        high = _time_edit_to_seconds(self.duration_max_edit)
        low = _time_edit_to_seconds(self.duration_min_edit) if not self.duration_min_none.isChecked() else None
        if low is not None and high < low:
            _seconds_to_time_edit(high, self.duration_min_edit)
        self._apply_filters()

    def _on_rating_from_changed(self) -> None:
        r_from = self.rating_from_combo.currentData()
        r_to = self.rating_to_combo.currentData()
        if r_from is not None and r_to is not None and r_from > r_to:
            self.rating_to_combo.blockSignals(True)
            self.rating_to_combo.setCurrentIndex(self.rating_from_combo.currentIndex())
            self.rating_to_combo.blockSignals(False)
        self._apply_filters()

    def _on_rating_to_changed(self) -> None:
        r_from = self.rating_from_combo.currentData()
        r_to = self.rating_to_combo.currentData()
        if r_from is not None and r_to is not None and r_to < r_from:
            self.rating_from_combo.blockSignals(True)
            self.rating_from_combo.setCurrentIndex(self.rating_to_combo.currentIndex())
            self.rating_from_combo.blockSignals(False)
        self._apply_filters()

    def _on_last_played_mode_changed(self) -> None:
        is_time = self.last_played_mode_combo.currentData() == "time"
        self.last_played_from_combo.setVisible(is_time)
        self.last_played_to_combo.setVisible(is_time)
        self.last_played_from_dt.setVisible(not is_time)
        self.last_played_to_dt.setVisible(not is_time)
        self._apply_filters()

    def _on_last_played_from_time_changed(self) -> None:
        idx_from = self.last_played_from_combo.currentIndex()
        idx_to = self.last_played_to_combo.currentIndex()
        if idx_from > idx_to:
            self.last_played_to_combo.blockSignals(True)
            self.last_played_to_combo.setCurrentIndex(idx_from)
            self.last_played_to_combo.blockSignals(False)
        self._apply_filters()

    def _on_last_played_to_time_changed(self) -> None:
        idx_from = self.last_played_from_combo.currentIndex()
        idx_to = self.last_played_to_combo.currentIndex()
        if idx_to < idx_from:
            self.last_played_from_combo.blockSignals(True)
            self.last_played_from_combo.setCurrentIndex(idx_to)
            self.last_played_from_combo.blockSignals(False)
        self._apply_filters()

    def _on_last_played_from_date_changed(self) -> None:
        dt_from = self.last_played_from_dt.dateTime().toPython()
        dt_to = self.last_played_to_dt.dateTime().toPython()
        if dt_from > dt_to:
            self.last_played_to_dt.blockSignals(True)
            self.last_played_to_dt.setDateTime(self.last_played_from_dt.dateTime())
            self.last_played_to_dt.blockSignals(False)
        self._apply_filters()

    def _on_last_played_to_date_changed(self) -> None:
        dt_from = self.last_played_from_dt.dateTime().toPython()
        dt_to = self.last_played_to_dt.dateTime().toPython()
        if dt_to < dt_from:
            self.last_played_from_dt.blockSignals(True)
            self.last_played_from_dt.setDateTime(self.last_played_to_dt.dateTime())
            self.last_played_from_dt.blockSignals(False)
        self._apply_filters()

    def _on_parts_min_changed(self) -> None:
        lo = self.parts_min_combo.currentData()
        hi = self.parts_max_combo.currentData()
        if lo is not None and hi is not None and lo > hi:
            self.parts_max_combo.blockSignals(True)
            self.parts_max_combo.setCurrentIndex(self.parts_min_combo.currentIndex())
            self.parts_max_combo.blockSignals(False)
        self._apply_filters()

    def _on_parts_max_changed(self) -> None:
        lo = self.parts_min_combo.currentData()
        hi = self.parts_max_combo.currentData()
        if lo is not None and hi is not None and hi < lo:
            self.parts_min_combo.blockSignals(True)
            self.parts_min_combo.setCurrentIndex(self.parts_max_combo.currentIndex())
            self.parts_min_combo.blockSignals(False)
        self._apply_filters()

    def _on_status_filter_clicked(self) -> None:
        if self._status_just_closed:
            return
        if self._status_popup is not None:
            if self._status_popup.isVisible():
                self._status_popup.close()
                self.status_btn.setChecked(False)
                return
            self._status_popup = None

        popup = QFrame(self, Qt.WindowType.Popup)
        popup.setMaximumWidth(260)
        layout = QVBoxLayout(popup)
        layout.setContentsMargins(0, 0, 0, 0)
        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 10, 12, 8)
        header_layout.addWidget(QLabel("Filter by status"))
        header_layout.addStretch()
        layout.addWidget(header)

        scroll = QScrollArea()
        scroll.setMaximumHeight(280)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(12, 8, 12, 12)
        content_layout.setSpacing(4)
        statuses = list_statuses(self.app_state.conn)
        chips: list[tuple[QPushButton, int | None]] = []

        def update_chip_styles() -> None:
            for btn, sid in chips:
                selected = (sid is None and not self._selected_status_ids) or (
                    sid is not None and sid in self._selected_status_ids
                )
                left = COLOR_OUTLINE_VARIANT
                if sid is not None:
                    for r in statuses:
                        if r.id == sid:
                            left = r.color if r.color else COLOR_OUTLINE_VARIANT
                            try:
                                QColor(left)
                            except Exception:
                                left = COLOR_OUTLINE_VARIANT
                            break
                btn.setStyleSheet(_status_chip_style(left, selected))

        def update_button_text() -> None:
            n = len(self._selected_status_ids)
            self.status_btn.setText(
                "All statuses" if n == 0 else ("1 status" if n == 1 else f"{n} statuses")
            )

        def on_chip_clicked(status_id: int | None) -> None:
            if status_id is None:
                self._selected_status_ids = []
            elif status_id in self._selected_status_ids:
                self._selected_status_ids = [x for x in self._selected_status_ids if x != status_id]
            else:
                self._selected_status_ids = self._selected_status_ids + [status_id]
            update_chip_styles()
            update_button_text()
            QTimer.singleShot(0, self._apply_filters)

        all_chip = QPushButton("All statuses")
        all_chip.setCursor(Qt.CursorShape.PointingHandCursor)
        chips.append((all_chip, None))
        content_layout.addWidget(all_chip)
        all_chip.clicked.connect(lambda: on_chip_clicked(None))
        for r in statuses:
            chip = QPushButton(r.name)
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chips.append((chip, r.id))
            content_layout.addWidget(chip)
            chip.clicked.connect(lambda checked=False, sid=r.id: on_chip_clicked(sid))
        content_layout.addStretch()
        scroll.setWidget(content)
        layout.addWidget(scroll)
        update_chip_styles()

        def on_status_popup_hidden() -> None:
            self._status_popup = None
            try:
                self.status_btn.setChecked(False)
            except RuntimeError:
                pass
            self._status_just_closed = True
            if self._status_just_closed_timer is not None:
                self._status_just_closed_timer.stop()
            self._status_just_closed_timer = QTimer(self)
            self._status_just_closed_timer.setSingleShot(True)
            self._status_just_closed_timer.timeout.connect(lambda: setattr(self, "_status_just_closed", False))
            self._status_just_closed_timer.start(300)

        popup.installEventFilter(_PopupHideFilter(popup, on_status_popup_hidden, self))
        popup.move(self.status_btn.mapToGlobal(self.status_btn.rect().bottomLeft()))
        popup.show()
        self._status_popup = popup
        self._status_just_closed = False

    def _on_transcriber_filter_clicked(self) -> None:
        if self._transcriber_just_closed:
            return
        if self._transcriber_popup is not None:
            if self._transcriber_popup.isVisible():
                self._transcriber_popup.close()
                self.transcriber_btn.setChecked(False)
                return
            self._transcriber_popup = None

        popup = QFrame(self, Qt.WindowType.Popup)
        popup.setMaximumWidth(260)
        layout = QVBoxLayout(popup)
        layout.setContentsMargins(0, 0, 0, 0)
        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 10, 12, 8)
        header_layout.addWidget(QLabel("Filter by transcriber"))
        header_layout.addStretch()
        layout.addWidget(header)

        scroll = QScrollArea()
        scroll.setMaximumHeight(280)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(12, 8, 12, 12)
        content_layout.setSpacing(4)
        transcribers = list_unique_transcribers(self.app_state.conn)
        chips: list[tuple[QPushButton, str | None]] = []

        def update_chip_styles() -> None:
            for btn, t in chips:
                selected = (t is None and not self._selected_transcribers) or (
                    t is not None and t in self._selected_transcribers
                )
                btn.setStyleSheet(_transcriber_chip_style(selected))

        def update_button_text() -> None:
            n = len(self._selected_transcribers)
            self.transcriber_btn.setText(
                "All transcribers" if n == 0 else ("1 transcriber" if n == 1 else f"{n} transcribers")
            )

        def on_chip_clicked(transcriber: str | None) -> None:
            if transcriber is None:
                self._selected_transcribers = []
            elif transcriber in self._selected_transcribers:
                self._selected_transcribers = [x for x in self._selected_transcribers if x != transcriber]
            else:
                self._selected_transcribers = self._selected_transcribers + [transcriber]
            update_chip_styles()
            update_button_text()
            QTimer.singleShot(0, self._apply_filters)

        all_chip = QPushButton("All transcribers")
        all_chip.setCursor(Qt.CursorShape.PointingHandCursor)
        chips.append((all_chip, None))
        content_layout.addWidget(all_chip)
        all_chip.clicked.connect(lambda: on_chip_clicked(None))
        for t in transcribers:
            chip = QPushButton(t)
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chips.append((chip, t))
            content_layout.addWidget(chip)
            chip.clicked.connect(lambda checked=False, tr=t: on_chip_clicked(tr))
        content_layout.addStretch()
        scroll.setWidget(content)
        layout.addWidget(scroll)
        update_chip_styles()

        def on_transcriber_popup_hidden() -> None:
            self._transcriber_popup = None
            try:
                self.transcriber_btn.setChecked(False)
            except RuntimeError:
                pass
            self._transcriber_just_closed = True
            if self._transcriber_just_closed_timer is not None:
                self._transcriber_just_closed_timer.stop()
            self._transcriber_just_closed_timer = QTimer(self)
            self._transcriber_just_closed_timer.setSingleShot(True)
            self._transcriber_just_closed_timer.timeout.connect(lambda: setattr(self, "_transcriber_just_closed", False))
            self._transcriber_just_closed_timer.start(300)

        popup.installEventFilter(_PopupHideFilter(popup, on_transcriber_popup_hidden, self))
        popup.move(self.transcriber_btn.mapToGlobal(self.transcriber_btn.rect().bottomLeft()))
        popup.show()
        self._transcriber_popup = popup
        self._transcriber_just_closed = False


def open_library_picker_dialog(
    app_state: AppState,
    setlist_id: int,
    parent: QWidget | None = None,
    *,
    on_song_added: Callable[[int], None] | None = None,
) -> None:
    """Show the library picker; stays open until the user clicks Done."""
    initial = list_library_songs(app_state.conn, limit=1)
    if not initial:
        QMessageBox.information(parent, "Info", "No songs in library. Scan library first.")
        return
    dlg = LibraryPickerDialog(app_state, setlist_id, parent)
    if on_song_added is not None:
        dlg.songAdded.connect(on_song_added)
    dlg.exec()
