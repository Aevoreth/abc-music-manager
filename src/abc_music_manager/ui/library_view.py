"""
Library view: filterable table of songs, opens Song Detail on selection.
"""

from __future__ import annotations

import json
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
    QStyledItemDelegate,
    QDateTimeEdit,
    QStyleOptionViewItem,
    QStyle,
)
from PySide6.QtCore import Qt, QAbstractTableModel, QModelIndex, QSortFilterProxyModel, QRect, QSize, Signal
from PySide6.QtGui import QColor, QAction, QPainter, QFont, QBrush, QPen, QIcon, QPixmap

from ..services.app_state import AppState
from ..db import list_library_songs, get_status_list, LibrarySongRow
from ..db.status_repo import list_statuses
from ..db.setlist_repo import (
    list_setlists,
    add_setlist_item,
    list_setlist_items,
    get_setlists_containing_song,
)
from ..db.song_layout_repo import list_song_layouts_for_song_and_band
from ..db.play_log import log_play, log_play_at, get_play_history
from ..db.song_repo import update_song_app_metadata
from .theme import STATUS_CIRCLE_DIAMETER

# Role for status color in library filter combo items
LibraryStatusColorRole = Qt.ItemDataRole.UserRole + 20


class LibraryFilterStatusDelegate(QStyledItemDelegate):
    """Paints filter combo items with colored circle before the status name."""

    def paint(self, painter: QPainter, option, index) -> None:
        text = index.data(Qt.ItemDataRole.DisplayRole) or ""
        color = index.data(LibraryStatusColorRole)
        opt = QStyleOptionViewItem(option)
        rect = opt.rect.adjusted(2, 0, -2, 0)
        cy = rect.center().y()
        r = STATUS_CIRCLE_DIAMETER // 2
        try:
            qcolor = QColor(color) if color else opt.palette.color(opt.palette.currentColorGroup(), opt.palette.ColorRole.Mid)
        except Exception:
            qcolor = opt.palette.color(opt.palette.currentColorGroup(), opt.palette.ColorRole.Mid)
        painter.save()
        painter.setBrush(qcolor)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(rect.x(), cy - r, STATUS_CIRCLE_DIAMETER, STATUS_CIRCLE_DIAMETER)
        painter.setPen(QPen(opt.palette.text().color()))
        painter.drawText(rect.adjusted(STATUS_CIRCLE_DIAMETER + 4, 0, 0, 0), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, text)
        painter.restore()


def _status_icon_for_color(color: str | None, fallback: QColor) -> QIcon:
    """Return a QIcon with a colored circle for use in menus."""
    size = STATUS_CIRCLE_DIAMETER + 4
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    try:
        qcolor = QColor(color) if color else fallback
    except Exception:
        qcolor = fallback
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(qcolor)
    painter.setPen(Qt.PenStyle.NoPen)
    r = STATUS_CIRCLE_DIAMETER // 2
    painter.drawEllipse(2, 2, STATUS_CIRCLE_DIAMETER, STATUS_CIRCLE_DIAMETER)
    painter.end()
    return QIcon(pix)


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


def _part_names_from_json(parts_json: Optional[str]) -> list[str]:
    """Return list of part display names (part_name or 'Part N') from Song.parts JSON."""
    if not parts_json:
        return []
    try:
        parts = json.loads(parts_json)
        out = []
        for p in parts:
            name = (p.get("part_name") or "").strip()
            if not name:
                name = f"Part {p.get('part_number', len(out) + 1)}"
            out.append(name)
        return out
    except (json.JSONDecodeError, TypeError):
        return []


# Custom data roles for delegate
RowDataRole = Qt.ItemDataRole.UserRole + 1
StatusColorRole = Qt.ItemDataRole.UserRole + 2


class LibraryTableModel(QAbstractTableModel):
    """Table model for library songs. Refreshes from list_library_songs with current filters."""

    COLUMNS = [
        "Title",
        "Composer(s)",
        "Duration",
        "Last played",
        "",  # Play / Set / History buttons
        "Parts / Rating",
        "Set",
        "Status",
        "Transcriber",
    ]

    def __init__(self, conn, parent=None) -> None:
        super().__init__(parent)
        self._conn = conn
        self._rows: list[LibrarySongRow] = []
        self._filter_title_composer: str = ""
        self._filter_transcriber: str = ""
        self._filter_duration_min: Optional[int] = None
        self._filter_duration_max: Optional[int] = None
        self._filter_rating_min: Optional[int] = None
        self._filter_rating_max: Optional[int] = None
        self._filter_status_ids: Optional[list[int]] = None
        self._filter_part_count_min: Optional[int] = None
        self._filter_part_count_max: Optional[int] = None
        self._filter_plays_days: Optional[int] = None
        self._default_status_name: Optional[str] = None
        self._default_status_color: Optional[str] = None

    def set_filters(
        self,
        title_or_composer: str = "",
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
        self._filter_title_composer = (title_or_composer or "").strip()
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

    def _resolve_default_status(self) -> None:
        from ..db.status_repo import list_statuses, get_effective_default_status_id
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
        c = index.column()
        if role == RowDataRole:
            return row
        if role == Qt.ItemDataRole.DisplayRole:
            if c == 0:
                return row.title
            if c == 1:
                return row.composers
            if c == 2:
                return _format_duration(row.duration_seconds) or "—"
            if c == 3:
                return None  # Painted by delegate (last played)
            if c == 4:
                return None  # Painted by delegate (Play / Set / History buttons)
            if c == 5:
                return None  # Painted by delegate (parts / rating)
            if c == 6:
                return "•" if row.in_upcoming_set else ""
            if c == 7:
                return row.status_name or self._default_status_name or "—"
            if c == 8:
                return row.transcriber or "—"
        if role == StatusColorRole and c == 7:
            return row.status_color or self._default_status_color
        if role == Qt.ItemDataRole.ToolTipRole:
            if c == 4:
                return "▶ Played Now — Set… set date/time — History: playback log"
            if c == 5:
                parts = _part_names_from_json(row.parts_json)
                if parts:
                    return "Parts:\n" + "\n".join(parts)
            if c == 6:
                sets_list = get_setlists_containing_song(self._conn, row.song_id)
                if sets_list:
                    return "In sets:\n" + "\n".join(name for _, name in sets_list)
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


class LibrarySortProxy(QSortFilterProxyModel):
    """Sort by Title or Composer; default Title A->Z."""

    def lessThan(self, left: QModelIndex, right: QModelIndex) -> bool:
        lv = left.data(Qt.ItemDataRole.DisplayRole) or ""
        rv = right.data(Qt.ItemDataRole.DisplayRole) or ""
        return (lv or "").lower() < (rv or "").lower()


class LibraryDelegate(QStyledItemDelegate):
    """Paints Last played, Parts/Rating, Set, Status; simple text for others (Duration, etc.)."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        # Never show hover or focus bright highlight — only selection (row highlight) is used
        option.state &= ~(QStyle.StateFlag.State_MouseOver | QStyle.StateFlag.State_HasFocus)
        col = index.column()
        row_data = index.data(RowDataRole)
        if row_data is None and col not in (3, 4, 5, 6, 7):
            return super().paint(painter, option, index)

        if col == 3 and row_data:
            self._paint_last_played(painter, option, row_data)
            return
        if col == 4 and row_data:
            self._paint_play_buttons(painter, option)
            return
        if col == 5 and row_data:
            self._paint_parts_rating(painter, option, row_data)
            return
        if col == 6:
            if row_data and row_data.in_upcoming_set:
                self._paint_bullet(painter, option)
            return
        if col == 7 and row_data:
            self._paint_status(painter, option, row_data, index)
            return
        super().paint(painter, option, index)

    def _paint_last_played(self, painter: QPainter, option: QStyleOptionViewItem, row: LibrarySongRow) -> None:
        rect = option.rect.adjusted(2, 1, -2, -1)
        last_played = _format_last_played(row.last_played_at)
        painter.drawText(rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, last_played)

    def _paint_play_buttons(self, painter: QPainter, option: QStyleOptionViewItem) -> None:
        rect = option.rect.adjusted(2, 1, -2, -1)
        btn_h = 22
        line_h = option.fontMetrics.lineSpacing()
        btn_y = rect.y() + (2 * line_h - btn_h) // 2
        play_w, set_w, history_w = 28, 40, 52
        gap = 4
        margin = 4
        history_rect = QRect(rect.right() - margin - history_w, btn_y, history_w, btn_h)
        set_rect = QRect(history_rect.left() - gap - set_w, btn_y, set_w, btn_h)
        play_rect = QRect(set_rect.left() - gap - play_w, btn_y, play_w, btn_h)
        for r, label in [(play_rect, "▶"), (set_rect, "Set…"), (history_rect, "History")]:
            painter.setPen(QPen(option.palette.color(option.palette.currentColorGroup(), option.palette.ColorRole.Mid)))
            painter.setBrush(QBrush(option.palette.button()))
            painter.drawRoundedRect(r, 3, 3)
            painter.setPen(QPen(option.palette.color(option.palette.currentColorGroup(), option.palette.ColorRole.ButtonText)))
            painter.drawText(r, Qt.AlignmentFlag.AlignCenter, label)

    def _paint_parts_rating(self, painter: QPainter, option: QStyleOptionViewItem, row: LibrarySongRow) -> None:
        rect = option.rect.adjusted(2, 1, -2, -1)
        painter.drawText(rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, str(row.part_count))
        line_h = option.fontMetrics.lineSpacing()
        star_y = rect.y() + line_h + 1
        star_x = rect.x()
        rating = row.rating if row.rating is not None else 0
        filled = "\u2605"  # ★
        empty = "\u2606"   # ☆
        for i in range(1, 6):
            char = filled if i <= rating else empty
            color = QColor(255, 200, 0) if i <= rating else option.palette.color(option.palette.currentColorGroup(), option.palette.ColorRole.Text)
            painter.setPen(QPen(color))
            painter.drawText(star_x + (i - 1) * 14, star_y, 14, line_h, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, char)

    def _paint_bullet(self, painter: QPainter, option: QStyleOptionViewItem) -> None:
        rect = option.rect
        cx = rect.x() + 8
        cy = rect.center().y()
        painter.setBrush(QBrush(option.palette.text().color()))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(cx - 3, cy - 3, 6, 6)

    def _paint_status(self, painter: QPainter, option: QStyleOptionViewItem, row: LibrarySongRow, index: QModelIndex) -> None:
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
        painter.drawText(rect.adjusted(STATUS_CIRCLE_DIAMETER + 4, 0, 0, 0), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, name)


class LibraryView(QWidget):
    """Library table with filter bar and open Song Detail on double-click."""

    navigateToSetlist = Signal(int)  # setlist_id

    def __init__(self, app_state: AppState, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.app_state = app_state
        layout = QVBoxLayout(self)

        # Filter row: single Title/Composer filter with clear button, applies immediately
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("Title / Composer:"))
        self.title_composer_edit = QLineEdit()
        self.title_composer_edit.setPlaceholderText("Filter by title or composer")
        self.title_composer_edit.setClearButtonEnabled(True)
        self.title_composer_edit.setMaximumWidth(240)
        self.title_composer_edit.textChanged.connect(self._apply_filters)
        filter_layout.addWidget(self.title_composer_edit)
        filter_layout.addWidget(QLabel("Status:"))
        self.status_combo = QComboBox()
        self.status_combo.setItemDelegate(LibraryFilterStatusDelegate(self.status_combo))
        self.status_combo.setMinimumWidth(140)
        self.status_combo.currentIndexChanged.connect(self._apply_filters)
        filter_layout.addWidget(self.status_combo)
        filter_layout.addWidget(QLabel("Plays in last (days):"))
        self.plays_days_spin = QSpinBox()
        self.plays_days_spin.setRange(0, 365)
        self.plays_days_spin.setSpecialValueText("—")
        self.plays_days_spin.setMaximumWidth(60)
        self.plays_days_spin.valueChanged.connect(self._apply_filters)
        filter_layout.addWidget(self.plays_days_spin)
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self._apply_filters)
        filter_layout.addWidget(self.refresh_btn)
        filter_layout.addStretch()
        layout.addLayout(filter_layout)

        self.model = LibraryTableModel(app_state.conn)
        self.proxy = LibrarySortProxy(self)
        self.proxy.setSourceModel(self.model)
        self.proxy.setSortCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.proxy.sort(0, Qt.SortOrder.AscendingOrder)

        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.table.setItemDelegate(LibraryDelegate(self.table))
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        hh = self.table.horizontalHeader()
        hh.setMinimumSectionSize(20)
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        hh.resizeSection(0, 280)
        # Column 4: Play/Set/History buttons — explicit width (model has no text so ResizeToContents would collapse it)
        hh.setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive)
        hh.resizeSection(4, 140)  # Wide enough for ▶ + Set… + History
        # Columns 5 (Parts/Rating), 6 (Set) size to contents; 8 (Transcriber) user-resizable
        hh.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(8, QHeaderView.ResizeMode.Interactive)
        hh.resizeSection(8, 120)
        hh.setSectionsClickable(True)
        hh.sectionClicked.connect(self._on_header_clicked)
        # Row height: 2 lines of text + padding
        fm = self.table.fontMetrics()
        line_h = fm.lineSpacing()
        row_height = 2 * line_h + 10
        self.table.verticalHeader().setDefaultSectionSize(row_height)
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self.table.setAlternatingRowColors(True)
        self.table.doubleClicked.connect(self._on_double_click)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_context_menu)
        self.table.viewport().installEventFilter(self)
        layout.addWidget(self.table)

        self._load_status_combo()
        self.model.refresh()

    def _on_header_clicked(self, logical_index: int) -> None:
        if logical_index not in (0, 1):
            return
        header = self.table.horizontalHeader()
        current_section = header.sortIndicatorSection()
        current_order = header.sortIndicatorOrder()
        if logical_index == current_section:
            new_order = Qt.SortOrder.DescendingOrder if current_order == Qt.SortOrder.AscendingOrder else Qt.SortOrder.AscendingOrder
        else:
            new_order = Qt.SortOrder.AscendingOrder  # First click on this column: A -> Z
        header.setSortIndicator(logical_index, new_order)
        self.proxy.sort(logical_index, new_order)

    def _source_row(self, proxy_index: QModelIndex) -> int:
        return self.proxy.mapToSource(proxy_index).row()

    def _song_id_for_proxy_row(self, proxy_row: int) -> Optional[int]:
        return self.model.song_id_at(self.proxy.mapToSource(self.proxy.index(proxy_row, 0)).row())

    def _row_for_proxy_row(self, proxy_row: int) -> Optional[LibrarySongRow]:
        return self.model.row_at(self.proxy.mapToSource(self.proxy.index(proxy_row, 0)).row())

    def eventFilter(self, obj, event) -> bool:
        from PySide6.QtCore import QEvent
        if obj is self.table.viewport():
            if event.type() == QEvent.Type.Leave:
                # Qt does not repaint on Leave/HoverLeave, so hover highlight can get stuck.
                self.table.viewport().update()
                return False
            if event.type() == QEvent.Type.MouseButtonPress:
                pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
                index = self.table.indexAt(pos)
                if not index.isValid():
                    return False
                proxy_row = index.row()
                col = index.column()
                source_row = self._source_row(index)
                row_data = self.model.row_at(source_row)
                if not row_data:
                    return False
                song_id = row_data.song_id
                rect = self.table.visualRect(index)
                x = pos.x() - rect.x()
                y = pos.y() - rect.y()
                if col == 4:
                    # Buttons from right: History w=52, gap 4, Set w=40, gap 4, Play w=28, margin 4
                    rx = rect.width() - x
                    if 4 <= rx <= 56:
                        self._on_play_history(song_id, row_data.title)
                        return True
                    if 60 <= rx <= 100:
                        self._on_set_play_time(song_id)
                        return True
                    if 104 <= rx <= 132:
                        self._on_played_now(song_id)
                        return True
                if col == 5:
                    # Star hit test: 5 stars, each 14px wide
                    line_h = self.table.fontMetrics().lineSpacing()
                    if y > line_h:
                        star_idx = min(5, max(1, int(x / 14) + 1))
                        if 1 <= star_idx <= 5:
                            current = row_data.rating if row_data.rating is not None else 0
                            if current == star_idx:
                                new_rating = 0
                            else:
                                new_rating = star_idx
                            update_song_app_metadata(self.app_state.conn, song_id, rating=new_rating)
                            self.model.refresh()
                        return True
                if col == 6 and row_data.in_upcoming_set:
                    sets_list = get_setlists_containing_song(self.app_state.conn, song_id)
                    if sets_list:
                        menu = QMenu(self)
                        for setlist_id, setlist_name in sets_list:
                            act = menu.addAction(f"Go to: {setlist_name}")
                            act.triggered.connect(lambda checked=False, sid=setlist_id: self._go_to_setlist(sid))
                        menu.exec(self.table.viewport().mapToGlobal(pos))
                    return True
                if col == 7:
                    # Status: show dropdown to set song status (songs always have a status)
                    menu = QMenu(self)
                    fallback = self.palette().color(self.palette().currentColorGroup(), self.palette().ColorRole.Mid)
                    for r in list_statuses(self.app_state.conn):
                        icon = _status_icon_for_color(r.color, fallback)
                        act = menu.addAction(icon, r.name)
                        act.triggered.connect(lambda checked=False, sid=r.id: self._set_song_status(song_id, sid))
                        if row_data.status_id == r.id:
                            act.setCheckable(True)
                            act.setChecked(True)
                    menu.exec(self.table.viewport().mapToGlobal(pos))
                    return True
        return False

    def _go_to_setlist(self, setlist_id: int) -> None:
        self.navigateToSetlist.emit(setlist_id)

    def _set_song_status(self, song_id: int, status_id: Optional[int]) -> None:
        update_song_app_metadata(self.app_state.conn, song_id, status_id=status_id)
        self.model.refresh()

    def _on_played_now(self, song_id: int) -> None:
        log_play(self.app_state.conn, song_id)
        self.model.refresh()

    def _on_play_history(self, song_id: int, song_title: str) -> None:
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QTextEdit, QDialogButtonBox
        history = get_play_history(self.app_state.conn, song_id)
        dlg = QDialog(self)
        dlg.setWindowTitle(f"Play history — {song_title}")
        layout = QVBoxLayout(dlg)
        text = QTextEdit(dlg)
        text.setReadOnly(True)
        if not history:
            text.setPlainText("No plays recorded.")
        else:
            lines = []
            for played_at_iso, setlist_name, context_note in history:
                try:
                    dt = datetime.fromisoformat(played_at_iso.replace("Z", "+00:00"))
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    local = dt.astimezone()
                    when = local.strftime("%Y-%m-%d %H:%M")
                except Exception:
                    when = played_at_iso
                parts = [when]
                if setlist_name:
                    parts.append(f"Set: {setlist_name}")
                if context_note:
                    parts.append(context_note)
                lines.append("  |  ".join(parts))
            text.setPlainText("\n".join(lines))
        layout.addWidget(text)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        bb.accepted.connect(dlg.accept)
        layout.addWidget(bb)
        dlg.resize(480, 320)
        dlg.exec()

    def _on_set_play_time(self, song_id: int) -> None:
        from PySide6.QtWidgets import QDialog, QDialogButtonBox
        dlg = QDialog(self)
        dlg.setWindowTitle("Set last played")
        layout = QVBoxLayout(dlg)
        dt_edit = QDateTimeEdit(dlg)
        dt_edit.setCalendarPopup(True)
        dt_edit.setDateTime(datetime.now(timezone.utc))
        layout.addWidget(dt_edit)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        layout.addWidget(bb)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            dt = dt_edit.dateTime().toPython()
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            log_play_at(self.app_state.conn, song_id, dt.isoformat())
            self.model.refresh()

    def _load_status_combo(self) -> None:
        self.status_combo.clear()
        self.status_combo.addItem("(all)", None)
        for r in list_statuses(self.app_state.conn):
            i = self.status_combo.count()
            self.status_combo.addItem(r.name, r.id)
            self.status_combo.setItemData(i, r.color, LibraryStatusColorRole)

    def _apply_filters(self) -> None:
        status_data = self.status_combo.currentData()
        status_ids = [status_data] if status_data is not None and status_data != -1 else None
        plays_days = self.plays_days_spin.value()
        if plays_days <= 0:
            plays_days = None
        self.model.set_filters(
            title_or_composer=self.title_composer_edit.text(),
            status_ids=status_ids,
            plays_days=plays_days,
        )

    def _on_double_click(self, index: QModelIndex) -> None:
        source_index = self.proxy.mapToSource(index)
        song_id = self.model.song_id_at(source_index.row())
        if song_id is not None:
            self._open_song_detail(song_id)

    def _on_context_menu(self, pos) -> None:
        index = self.table.indexAt(pos)
        if not index.isValid():
            return
        source_row = self._source_row(index)
        song_id = self.model.song_id_at(source_row)
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
