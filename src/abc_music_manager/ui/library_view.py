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
    QGridLayout,
    QTableView,
    QLineEdit,
    QLabel,
    QComboBox,
    QSpinBox,
    QPushButton,
    QCheckBox,
    QAbstractItemView,
    QHeaderView,
    QMessageBox,
    QMenu,
    QStyledItemDelegate,
    QDateTimeEdit,
    QTimeEdit,
    QStyleOptionComboBox,
    QStyleOptionViewItem,
    QStyle,
    QFrame,
    QListWidget,
    QListWidgetItem,
    QScrollArea,
    QApplication,
)
from PySide6.QtCore import Qt, QTime, QAbstractTableModel, QModelIndex, QSortFilterProxyModel, QRect, QSize, Signal, QTimer
from PySide6.QtGui import QColor, QAction, QPainter, QFont, QBrush, QPen, QIcon, QPixmap

from ..services.app_state import AppState
from ..db import list_library_songs, list_unique_transcribers, get_status_list, LibrarySongRow
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
from .theme import (
    STATUS_CIRCLE_DIAMETER,
    COLOR_SURFACE,
    COLOR_SURFACE_VARIANT,
    COLOR_OUTLINE,
    COLOR_OUTLINE_VARIANT,
    COLOR_PRIMARY,
    COLOR_TEXT_HEADER,
    COLOR_TEXT_SECONDARY,
    COLOR_ON_SURFACE,
)

# Role for status color in library filter combo items (menus, etc.)
LibraryStatusColorRole = Qt.ItemDataRole.UserRole + 20

# Status filter popup: chip button styles (no list widget = no delegate/model crash)
def _status_chip_style(left_color: str, selected: bool) -> str:
    bg = f"rgba(201, 162, 39, 0.15)" if selected else COLOR_SURFACE_VARIANT
    border = f"2px solid {COLOR_PRIMARY}" if selected else f"1px solid {COLOR_OUTLINE}"
    text = COLOR_TEXT_HEADER if selected else COLOR_TEXT_SECONDARY
    return (
        f"QPushButton {{ "
        f"text-align: left; padding: 6px 10px 6px 14px; "
        f"min-height: 24px; border: {border}; border-left: 4px solid {left_color}; "
        f"border-radius: 8px; background: {bg}; color: {text}; "
        f"}} QPushButton:hover {{ background: {COLOR_OUTLINE_VARIANT}; color: {COLOR_ON_SURFACE}; }}"
    )

# Last-played time-range options: (label, seconds_ago). "Never" = no upper bound (songs never played).
def _last_played_time_options() -> list[tuple[str, Optional[int]]]:
    opts: list[tuple[str, Optional[int]]] = []
    opts.append(("Just now", 0))
    for h in range(1, 24):
        opts.append((f"{h} hour(s)", h * 3600))
    for d in range(1, 14):
        opts.append((f"{d} day(s)", d * 86400))
    for w in range(2, 8):
        opts.append((f"{w} week(s)", w * 604800))
    for m in range(2, 24):
        opts.append((f"{m} month(s)", m * 30 * 86400))
    for y in range(1, 11):
        opts.append((f"{y} year(s)", y * 365 * 86400))
    opts.append(("Never", None))  # filter: never played
    return opts


LAST_PLAYED_TIME_OPTS = _last_played_time_options()

# Rating: 0 = no stars, 1-5 = star count (for combo display)
RATING_STAR_FILLED = "\u2605"
RATING_STAR_EMPTY = "\u2606"


# Gold for filled stars; gray for empty (so they're not white)
RATING_STAR_GOLD = QColor(255, 200, 0)
RATING_STAR_EMPTY_COLOR = QColor(128, 128, 128)


def _rating_label(stars: int) -> str:
    if stars <= 0:
        return "No stars"
    # Filled left to right: ★★★☆☆
    return RATING_STAR_FILLED * stars + RATING_STAR_EMPTY * (5 - stars)


def _paint_rating_stars(painter: QPainter, rect: QRect, rating: int, font_metrics, palette=None) -> None:
    """Draw rating as stars (gold filled, gray empty) left to right. rating 0 = five gray empty stars."""
    line_h = font_metrics.lineSpacing()
    star_y = rect.center().y() - line_h // 2
    star_x = rect.x()
    for i in range(1, 6):
        filled = rating > 0 and i <= rating
        char = RATING_STAR_FILLED if filled else RATING_STAR_EMPTY
        color = RATING_STAR_GOLD if filled else RATING_STAR_EMPTY_COLOR
        painter.setPen(QPen(color))
        painter.drawText(star_x + (i - 1) * 14, star_y, 14, line_h, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, char)


# Width for 5 stars at 14px each + padding + dropdown arrow (avoid clipping last star)
RATING_COMBO_MIN_WIDTH = 108


class RatingComboBox(QComboBox):
    """Combo that shows the selected rating as gold/gray stars when closed and in the dropdown."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(RATING_COMBO_MIN_WIDTH)

    def paintEvent(self, event) -> None:
        opt = QStyleOptionComboBox()
        self.initStyleOption(opt)
        style = self.style()
        painter = QPainter(self)
        style.drawComplexControl(QStyle.ComplexControl.CC_ComboBox, opt, painter, self)
        edit_rect = style.subControlRect(
            QStyle.ComplexControl.CC_ComboBox, opt, QStyle.SubControl.SC_ComboBoxEditField, self
        )
        if edit_rect.isValid():
            painter.fillRect(edit_rect, self.palette().color(self.palette().currentColorGroup(), self.palette().ColorRole.Base))
            rating = self.currentData()
            rating = int(rating) if rating is not None else 0
            _paint_rating_stars(painter, edit_rect.adjusted(2, 0, -2, 0), rating, self.fontMetrics(), self.palette())
        painter.end()


class RatingComboDelegate(QStyledItemDelegate):
    """Paints rating combo dropdown items as stars (filled left to right, gold filled / gray empty)."""

    def paint(self, painter: QPainter, option, index) -> None:
        text = index.data(Qt.ItemDataRole.DisplayRole) or ""
        opt = QStyleOptionViewItem(option)
        rect = opt.rect.adjusted(2, 0, -2, 0)
        rating = index.data(Qt.ItemDataRole.UserRole)
        if rating is None:
            painter.drawText(rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, text)
            return
        rating = int(rating) if rating is not None else 0
        _paint_rating_stars(painter, rect, rating, opt.fontMetrics, opt.palette)


def _time_edit_to_seconds(edit: QTimeEdit) -> int:
    """Return total seconds from a QTimeEdit used for duration (0:00:00 = 0 sec)."""
    t = edit.time()
    return t.hour() * 3600 + t.minute() * 60 + t.second()


def _seconds_to_time_edit(seconds: int, edit: QTimeEdit) -> None:
    """Set QTimeEdit from total seconds (duration). Clamps to 0–23:59:59."""
    sec = max(0, min(seconds, 23 * 3600 + 59 * 60 + 59))
    edit.blockSignals(True)
    edit.setTime(QTime(0, 0, 0).addSecs(sec))
    edit.blockSignals(False)


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


# Custom data roles for delegate and sorting
RowDataRole = Qt.ItemDataRole.UserRole + 1
StatusColorRole = Qt.ItemDataRole.UserRole + 2
SortRole = Qt.ItemDataRole.UserRole + 3


class LibraryTableModel(QAbstractTableModel):
    """Table model for library songs. Refreshes from list_library_songs with current filters."""

    COLUMNS = [
        "Title",
        "Composer(s)",
        "Duration",
        "Last played",
        "",  # Play / Set / History buttons
        "Parts",
        "Rating",
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
        self._filter_in_set: Optional[str] = None  # "yes", "no", or None for either
        self._default_status_name: Optional[str] = None
        self._default_status_color: Optional[str] = None

    def set_filters(
        self,
        title_or_composer: str = "",
        transcriber: str = "",
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
        self._filter_transcriber = (transcriber or "").strip()
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
                return str(row.part_count)
            if c == 6:
                return None  # Painted by delegate (rating stars)
            if c == 7:
                return "•" if row.in_upcoming_set else ""
            if c == 8:
                return row.status_name or self._default_status_name or "—"
            if c == 9:
                return row.transcriber or "—"
        if role == SortRole:
            if c == 2:
                return row.duration_seconds if row.duration_seconds is not None else -1
            if c == 3:
                return row.last_played_at or ""  # ISO string, empty = never played
            if c == 5:
                return row.part_count
            if c == 6:
                return row.rating if row.rating is not None else -1
        if role == StatusColorRole and c == 8:
            return row.status_color or self._default_status_color
        if role == Qt.ItemDataRole.ToolTipRole:
            if c == 4:
                return "▶ Played Now — Set… set date/time — History: playback log"
            if c == 5:
                parts = _part_names_from_json(row.parts_json)
                if parts:
                    return "Parts:\n" + "\n".join(parts)
            if c == 7:
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
    """Sort by any sortable column using SortRole when set, else DisplayRole."""

    def lessThan(self, left: QModelIndex, right: QModelIndex) -> bool:
        left_sort = left.data(SortRole)
        right_sort = right.data(SortRole)
        if left_sort is not None and right_sort is not None:
            if isinstance(left_sort, int) and isinstance(right_sort, int):
                return left_sort < right_sort
            if isinstance(left_sort, str) and isinstance(right_sort, str):
                return left_sort.lower() < right_sort.lower()
        lv = left.data(Qt.ItemDataRole.DisplayRole) or ""
        rv = right.data(Qt.ItemDataRole.DisplayRole) or ""
        return (str(lv) or "").lower() < (str(rv) or "").lower()


class LibraryDelegate(QStyledItemDelegate):
    """Paints Last played, Parts, Rating, Set, Status; simple text for others (Duration, etc.)."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        # Never show hover or focus bright highlight — only selection (row highlight) is used
        option.state &= ~(QStyle.StateFlag.State_MouseOver | QStyle.StateFlag.State_HasFocus)
        col = index.column()
        row_data = index.data(RowDataRole)
        if row_data is None and col not in (3, 4, 5, 6, 7, 8):
            return super().paint(painter, option, index)

        if col == 3 and row_data:
            self._paint_last_played(painter, option, row_data)
            return
        if col == 4 and row_data:
            self._paint_play_buttons(painter, option)
            return
        if col == 5 and row_data:
            self._paint_parts(painter, option, row_data)
            return
        if col == 6 and row_data:
            self._paint_rating(painter, option, row_data)
            return
        if col == 7:
            if row_data and row_data.in_upcoming_set:
                self._paint_bullet(painter, option)
            return
        if col == 8 and row_data:
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

    def _paint_parts(self, painter: QPainter, option: QStyleOptionViewItem, row: LibrarySongRow) -> None:
        rect = option.rect.adjusted(2, 1, -2, -1)
        painter.drawText(rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, str(row.part_count))

    def _paint_rating(self, painter: QPainter, option: QStyleOptionViewItem, row: LibrarySongRow) -> None:
        rect = option.rect.adjusted(2, 1, -2, -1)
        star_x = rect.x()
        cy = rect.center().y()
        line_h = option.fontMetrics.lineSpacing()
        star_y = cy - line_h // 2
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

        # ---- Main filter row: Title/Composer, Status, In set, Rating from/to, More Filters ----
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
        self.status_btn.setToolTip("Filter by status")
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
        self.rating_to_combo.setCurrentIndex(5)  # 5 stars default
        self.rating_to_combo.currentIndexChanged.connect(self._on_rating_to_changed)
        main_row.addWidget(self.rating_to_combo)
        self.more_filters_btn = QPushButton("More Filters")
        self.more_filters_btn.setCheckable(True)
        self.more_filters_btn.toggled.connect(self._on_more_filters_toggled)
        main_row.addWidget(self.more_filters_btn)
        main_row.addStretch()
        filter_layout.addLayout(main_row)

        # ---- More Filters panel (collapsible) ----
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
        self.duration_min_edit.setMinimumTime(QTime(0, 0, 0))
        self.duration_min_edit.setMaximumTime(QTime(23, 59, 59))
        self.duration_min_edit.setTime(QTime(0, 0, 0))
        self.duration_min_edit.setMinimumWidth(88)
        self.duration_min_edit.setMaximumWidth(96)
        self.duration_min_edit.timeChanged.connect(self._on_duration_min_changed)
        self.duration_min_edit.setEnabled(False)
        more_row1.addWidget(self.duration_min_edit)
        more_row1.addWidget(QLabel("to"))
        self.duration_max_none = QCheckBox("None")
        self.duration_max_none.setChecked(True)
        self.duration_max_none.toggled.connect(self._on_duration_none_toggled)
        more_row1.addWidget(self.duration_max_none)
        self.duration_max_edit = QTimeEdit()
        self.duration_max_edit.setDisplayFormat("m:ss")
        self.duration_max_edit.setMinimumTime(QTime(0, 0, 0))
        self.duration_max_edit.setMaximumTime(QTime(23, 59, 59))
        self.duration_max_edit.setTime(QTime(0, 20, 0))  # default upper bound 20:00
        self.duration_max_edit.setMinimumWidth(88)
        self.duration_max_edit.setMaximumWidth(96)
        self.duration_max_edit.timeChanged.connect(self._on_duration_max_changed)
        self.duration_max_edit.setEnabled(False)
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
        self.parts_min_combo.setCurrentIndex(0)
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
        self.transcriber_btn = QPushButton("All")
        self.transcriber_btn.setCheckable(True)
        self.transcriber_btn.clicked.connect(self._on_transcriber_filter_clicked)
        more_row2.addWidget(self.transcriber_btn)
        more_row2.addStretch()
        more_layout.addLayout(more_row2)
        self.more_filters_panel.setVisible(False)
        filter_layout.addWidget(self.more_filters_panel)

        layout.addWidget(filter_widget)

        self.model = LibraryTableModel(app_state.conn)
        self.proxy = LibrarySortProxy(self)
        self.proxy.setSourceModel(self.model)
        self.proxy.setSortCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._sort_column = 0
        self._sort_order = Qt.SortOrder.AscendingOrder
        self.proxy.sort(self._sort_column, self._sort_order)

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
        # Columns 5 (Parts), 6 (Rating), 7 (Set) size to contents; 9 (Transcriber) user-resizable
        hh.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(7, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(9, QHeaderView.ResizeMode.Interactive)
        hh.resizeSection(9, 120)
        hh.setSectionsClickable(True)
        hh.setSortIndicatorShown(True)
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

        self._selected_status_ids: list[int] = []
        self._status_popup: QWidget | None = None
        self._selected_transcribers: list[str] = []
        self._transcriber_popup: QWidget | None = None
        self.model.refresh()

    # Sortable columns: Title, Composer, Duration, Last played, Parts, Rating, Transcriber
    _SORTABLE_COLUMNS = (0, 1, 2, 3, 5, 6, 9)

    def _on_header_clicked(self, logical_index: int) -> None:
        if logical_index not in self._SORTABLE_COLUMNS:
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
                if col == 6:
                    # Rating: star hit test, 5 stars each 14px wide
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
                if col == 7 and row_data.in_upcoming_set:
                    sets_list = get_setlists_containing_song(self.app_state.conn, song_id)
                    if sets_list:
                        menu = QMenu(self)
                        for setlist_id, setlist_name in sets_list:
                            act = menu.addAction(f"Go to: {setlist_name}")
                            act.triggered.connect(lambda checked=False, sid=setlist_id: self._go_to_setlist(sid))
                        menu.exec(self.table.viewport().mapToGlobal(pos))
                    return True
                if col == 8:
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

    def _on_status_filter_clicked(self) -> None:
        if self._status_popup is not None and self._status_popup.isVisible():
            self._status_popup.close()
            self.status_btn.setChecked(False)
            return

        popup = QFrame(self, Qt.WindowType.Popup)
        popup.setObjectName("status_filter_popup")
        popup.setFrameShape(QFrame.Shape.StyledPanel)
        popup.setMaximumWidth(260)
        layout = QVBoxLayout(popup)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)

        header = QWidget()
        header.setObjectName("status_filter_header")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 10, 12, 8)
        header_layout.setSpacing(12)
        title_label = QLabel("Filter by status")
        title_label.setObjectName("status_filter_title")
        header_layout.addWidget(title_label)
        header_layout.addStretch()
        all_btn = QPushButton("All")
        all_btn.setObjectName("status_filter_header_btn")
        clear_btn = QPushButton("Clear")
        clear_btn.setObjectName("status_filter_header_btn")
        header_layout.addWidget(all_btn)
        header_layout.addWidget(clear_btn)
        layout.addWidget(header)

        # Chip buttons instead of QListWidget to avoid model/view crash on toggle
        scroll = QScrollArea()
        scroll.setObjectName("status_filter_list")
        scroll.setMaximumHeight(280)
        scroll.setMaximumWidth(240)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
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
                if sid is None:
                    left = COLOR_OUTLINE_VARIANT
                else:
                    left = COLOR_OUTLINE_VARIANT
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
            else:
                if status_id in self._selected_status_ids:
                    self._selected_status_ids = [x for x in self._selected_status_ids if x != status_id]
                else:
                    self._selected_status_ids = self._selected_status_ids + [status_id]
            update_chip_styles()
            update_button_text()
            QTimer.singleShot(0, self._apply_filters)

        # "All statuses" chip
        all_chip = QPushButton("All statuses")
        all_chip.setObjectName("status_filter_chip")
        all_chip.setCursor(Qt.CursorShape.PointingHandCursor)
        chips.append((all_chip, None))
        content_layout.addWidget(all_chip)
        all_chip.clicked.connect(lambda: on_chip_clicked(None))

        for r in statuses:
            chip = QPushButton(r.name)
            chip.setObjectName("status_filter_chip")
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chips.append((chip, r.id))
            content_layout.addWidget(chip)
            chip.clicked.connect(lambda checked=False, sid=r.id: on_chip_clicked(sid))

        content_layout.addStretch()
        scroll.setWidget(content)
        layout.addWidget(scroll)
        update_chip_styles()

        def reset_to_all() -> None:
            self._selected_status_ids = []
            update_chip_styles()
            update_button_text()
            QTimer.singleShot(0, self._apply_filters)

        all_btn.clicked.connect(reset_to_all)
        clear_btn.clicked.connect(reset_to_all)

        popup.move(self.status_btn.mapToGlobal(self.status_btn.rect().bottomLeft()))
        popup.show()
        self._status_popup = popup

        def on_popup_destroyed() -> None:
            self._status_popup = None
            try:
                self.status_btn.setChecked(False)
            except RuntimeError:
                pass

        popup.destroyed.connect(on_popup_destroyed)

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
            self.duration_max_edit.setTime(QTime(0, 20, 0))  # default upper bound when None unchecked
        self._apply_filters()

    def _on_duration_min_changed(self) -> None:
        if self.duration_min_none.isChecked():
            return
        low = _time_edit_to_seconds(self.duration_min_edit)
        high = (
            _time_edit_to_seconds(self.duration_max_edit)
            if not self.duration_max_none.isChecked()
            else None
        )
        if high is not None and low > high:
            _seconds_to_time_edit(low, self.duration_max_edit)
        self._apply_filters()

    def _on_duration_max_changed(self) -> None:
        if self.duration_max_none.isChecked():
            return
        high = _time_edit_to_seconds(self.duration_max_edit)
        low = (
            _time_edit_to_seconds(self.duration_min_edit)
            if not self.duration_min_none.isChecked()
            else None
        )
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

    def _on_transcriber_filter_clicked(self) -> None:
        if self._transcriber_popup is not None and self._transcriber_popup.isVisible():
            self._transcriber_popup.close()
            self.transcriber_btn.setChecked(False)
            return
        popup = QFrame(self, Qt.WindowType.Popup)
        popup.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout(popup)
        list_widget = QListWidget()
        list_widget.setMaximumHeight(220)
        list_widget.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        transcribers = list_unique_transcribers(self.app_state.conn)
        all_item = QListWidgetItem("[All]")
        all_item.setData(Qt.ItemDataRole.UserRole, None)
        list_widget.addItem(all_item)
        for t in transcribers:
            item = QListWidgetItem(t)
            item.setData(Qt.ItemDataRole.UserRole, t)
            list_widget.addItem(item)

        if not self._selected_transcribers:
            list_widget.item(0).setSelected(True)
        else:
            for i in range(1, list_widget.count()):
                if list_widget.item(i).data(Qt.ItemDataRole.UserRole) in self._selected_transcribers:
                    list_widget.item(i).setSelected(True)

        def on_selection_changed() -> None:
            selected = list_widget.selectedItems()
            has_all = any(it.data(Qt.ItemDataRole.UserRole) is None for it in selected)
            values = [] if has_all else [it.data(Qt.ItemDataRole.UserRole) for it in selected if it.data(Qt.ItemDataRole.UserRole) is not None]
            if not selected and list_widget.count():
                list_widget.blockSignals(True)
                list_widget.item(0).setSelected(True)
                list_widget.blockSignals(False)
                values = []
            self._selected_transcribers = values
            self.transcriber_btn.setText("All" if not self._selected_transcribers else f"Transcriber ({len(self._selected_transcribers)})")
            self._apply_filters()

        list_widget.itemSelectionChanged.connect(on_selection_changed)
        popup.move(self.transcriber_btn.mapToGlobal(self.transcriber_btn.rect().bottomLeft()))
        popup.show()

        def on_popup_closed():
            self._transcriber_popup = None
            try:
                self.transcriber_btn.setChecked(False)
            except RuntimeError:
                pass
        popup.destroyed.connect(on_popup_closed)
        self._transcriber_popup = popup

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
            idx_from = self.last_played_from_combo.currentIndex()
            idx_to = self.last_played_to_combo.currentIndex()
            sec_from = self.last_played_from_combo.currentData()
            sec_to = self.last_played_to_combo.currentData()
            if sec_to is None:
                last_played_never = True
            elif sec_from is not None or sec_to is not None:
                last_played_min_sec = sec_from  # From = newer (smaller seconds_ago)
                last_played_max_sec = sec_to    # To = older (larger seconds_ago)
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
            transcriber="",
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
