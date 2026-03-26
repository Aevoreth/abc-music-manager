"""
Setlist manager: band-style splitter, song table with live metadata, part assignments.
REQUIREMENTS §6.
"""

from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QSplitter,
    QStyleOptionViewItem,
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
    QTreeWidget,
    QTreeWidgetItem,
    QPlainTextEdit,
    QAbstractItemView,
    QHeaderView,
    QDateEdit,
    QTimeEdit,
    QScrollArea,
    QMenu,
    QStyledItemDelegate,
    QFrame,
    QFileDialog,
    QToolButton,
)
from PySide6.QtCore import Qt, QDate, QTime, QTimer, QMimeData, QSize, QRect, QPoint
from PySide6.QtGui import QColor, QFont, QDrag, QMouseEvent, QPixmap, QPainter

from ..services.app_state import AppState
from ..services.preferences import (
    DEFAULT_SETLISTS_EDITOR_SPLITTER_STATE,
    DEFAULT_SETLISTS_SONGS_TABLE_HEADER_STATE,
    DEFAULT_SETLISTS_SPLITTER_STATE,
    DEFAULT_SETLISTS_TOP_SPLIT_STATE,
    get_setlists_splitter_state,
    get_setlists_editor_splitter_state,
    get_setlists_top_split_state,
    get_setlists_songs_table_header_state,
    get_setlists_folder_expanded_state,
    set_setlists_splitter_state,
    set_setlists_editor_splitter_state,
    set_setlists_top_split_state,
    set_setlists_songs_table_header_state,
    set_setlists_folder_expanded_state,
)
from ..db import list_library_songs
from ..db.setlist_repo import (
    list_setlists,
    list_setlists_grouped_by_folder,
    add_setlist,
    update_setlist,
    delete_setlist,
    move_setlist_to_folder,
    list_setlist_items,
    list_setlist_items_with_song_meta,
    add_setlist_item,
    update_setlist_item,
    remove_setlist_item,
    reorder_setlist_items,
    merge_setlist_into,
    duplicate_setlist,
    get_setlist_band_assignments,
    SetlistRow,
    SetlistItemSongMetaRow,
)
from ..db.song_layout_repo import (
    list_song_layouts_for_song_and_band,
    add_song_layout,
    set_song_layout_assignment,
    get_song_layout_assignments,
    get_or_create_song_layout_for_band,
)
from ..db.song_repo import update_song_last_layout
from ..db.band_repo import list_all_band_layouts, list_layout_slots, list_band_members
from ..db.setlist_folder_repo import add_folder, update_folder, delete_folder, list_folders, reorder_folders
from ..db.player_repo import list_player_instruments_bulk
from ..db.instrument import get_instrument_ids_with_same_name_ci
from ..db.library_query import get_primary_file_path_for_song, get_song_id_for_file_path
from ..services.playback_state import PlaybackState, PlaylistEntry
from ..services.abcp_service import parse_abcp, write_abcp
from ..services.preferences import get_set_export_dir, resolve_music_path
from .setlist_band_assignment_panel import SetlistBandAssignmentPanel
from .set_export_dialog import SetExportDialog
from .theme import COLOR_ON_SURFACE, COLOR_PRIMARY


def _fmt_duration(sec: int | None) -> str:
    if sec is None or sec <= 0:
        return "—"
    m, s = divmod(int(sec), 60)
    if m >= 60:
        h, m = divmod(m, 60)
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def _fmt_setlist_display(s: SetlistRow) -> str:
    """Format setlist for tree: line 1 = outdented bullet + name, line 2 = date/time aligned with name."""
    indent = "    "  # Align name and date; bullet sits to the left
    name_line = f"•{indent}{s.name}"
    if s.set_date and s.set_time:
        date_line = f"{indent}{s.set_date} {s.set_time}"
    elif s.set_date:
        date_line = f"{indent}{s.set_date} --:--"
    else:
        date_line = f"{indent}—"
    return f"{name_line}\n{date_line}"


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
_MIME_SETLIST_ID = "application/x-setlist-id"
_MIME_FOLDER_ID = "application/x-folder-id"
_TYPE_ROLE = Qt.ItemDataRole.UserRole + 1
_PLACEHOLDER_ROLE = Qt.ItemDataRole.UserRole + 2


class SetlistTreeDelegate(QStyledItemDelegate):
    """Delegate that gives setlist/folder items enough height for two lines."""

    def sizeHint(self, option: QStyleOptionViewItem, index) -> QSize:
        size = super().sizeHint(option, index)
        fm = option.fontMetrics
        line_height = fm.lineSpacing()
        min_height = line_height * 2 + 6
        if size.height() < min_height:
            size.setHeight(min_height)
        return size


class SetlistTreeWidget(QTreeWidget):
    """Tree of folders and setlists. Supports drag-drop to move setlists and folders."""

    setlistMoved = None  # Set by parent: callable(setlist_id, target_folder_id, target_sort_order) -> None
    folderMoved = None  # Set by parent: callable(folder_ids_in_order: list[int], dragged_id: int, dragged_folder_expanded: bool | None) -> None
    onFolderDragStart = None  # Set by parent: callable() -> None, called before folder is removed (to save expanded state)
    onDragEnded = None  # Set by parent: callable() -> None, called when drag ends (for refresh on cancel)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._drag_item: QTreeWidgetItem | None = None
        self._drag_type: str = ""  # "setlist" or "folder"
        self._dragged_folder_expanded: bool | None = None
        self._placeholder_item: QTreeWidgetItem | None = None
        self._placeholder_folder: QTreeWidgetItem | None = None
        self._placeholder_index: int = 0
        self._placeholder_top_level_index: int = -1  # For folder drag (top-level placeholder)
        self._drop_line = QFrame(self.viewport())
        self._drop_line.setFixedHeight(3)
        self._drop_line.setStyleSheet(f"background-color: {COLOR_PRIMARY}; border: none;")
        self._drop_line.hide()
        self._folder_pressed: QTreeWidgetItem | None = None
        self._folder_expanded_at_press: bool | None = None
        self._did_drag = False

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        item = self.itemAt(event.position().toPoint())
        if item and item.data(0, _TYPE_ROLE) == "folder":
            self._folder_pressed = item
            self._folder_expanded_at_press = item.isExpanded()  # Before Qt processes
            self._did_drag = False
            super().mousePressEvent(event)
            return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            super().mouseReleaseEvent(event)
            return
        folder = self._folder_pressed
        did_drag = self._did_drag
        expanded_at_press = self._folder_expanded_at_press
        self._folder_pressed = None
        self._folder_expanded_at_press = None
        self._did_drag = False
        super().mouseReleaseEvent(event)
        # If user clicked folder label (not arrow): Qt didn't toggle, so we do.
        # Arrow clicks toggle on press; label clicks need our toggle on release.
        if folder and not did_drag and expanded_at_press is not None:
            item = self.itemAt(event.position().toPoint())
            if item is folder and folder.isExpanded() == expanded_at_press:
                folder.setExpanded(not expanded_at_press)

    def startDrag(self, supportedActions) -> None:
        self._did_drag = True

    def _make_drag_pixmap(self, item: QTreeWidgetItem) -> QPixmap:
        """Create a 75% opacity pixmap of the item for the drag preview."""
        index = self.indexFromItem(item, 0)
        rect = self.visualRect(index)
        if rect.width() <= 0 or rect.height() <= 0:
            rect = QRect(0, 0, 200, 40)
        pixmap = self.viewport().grab(rect)
        if pixmap.isNull():
            pixmap = QPixmap(max(200, rect.width()), max(40, rect.height()))
            pixmap.fill(Qt.GlobalColor.transparent)
        result = QPixmap(pixmap.size())
        result.fill(Qt.GlobalColor.transparent)
        painter = QPainter(result)
        painter.setOpacity(0.75)
        painter.drawPixmap(0, 0, pixmap)
        painter.end()
        return result

    def startDrag(self, supportedActions) -> None:
        item = self.currentItem()
        if not item:
            return
        typ = item.data(0, _TYPE_ROLE)
        if typ == "setlist":
            self._start_drag_setlist(item)
        elif typ == "folder" and item.parent() is None:
            folder_id = item.data(0, Qt.ItemDataRole.UserRole)
            if folder_id is not None:
                self._start_drag_folder(item)
        else:
            return

    def _start_drag_setlist(self, item: QTreeWidgetItem) -> None:
        setlist_id = item.data(0, Qt.ItemDataRole.UserRole)
        pixmap = self._make_drag_pixmap(item)
        index = self.indexFromItem(item, 0)
        initial_line_y = self.visualRect(index).top()
        self._drag_item = item
        self._drag_type = "setlist"
        parent = item.parent()
        if not parent:
            return
        origin_index = parent.indexOfChild(item)
        parent.takeChild(origin_index)
        self._placeholder_folder = parent
        self._placeholder_index = origin_index
        self._placeholder_top_level_index = -1
        self._placeholder_item = QTreeWidgetItem(parent, [" "])
        self._placeholder_item.setData(0, _PLACEHOLDER_ROLE, True)
        self._placeholder_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
        parent.insertChild(origin_index, self._placeholder_item)
        self._update_drop_line(y=initial_line_y)
        mime = QMimeData()
        mime.setData(_MIME_SETLIST_ID, str(setlist_id).encode("utf-8"))
        drag = QDrag(self)
        drag.setMimeData(mime)
        if not pixmap.isNull():
            drag.setPixmap(pixmap)
            drag.setHotSpot(pixmap.rect().center())
        drag.exec(Qt.DropAction.MoveAction)
        self._cleanup_after_drag()

    def _start_drag_folder(self, item: QTreeWidgetItem) -> None:
        if self.onFolderDragStart:
            self.onFolderDragStart()
        folder_id = item.data(0, Qt.ItemDataRole.UserRole)
        self._dragged_folder_expanded = item.isExpanded()
        pixmap = self._make_drag_pixmap(item)
        index = self.indexFromItem(item, 0)
        initial_line_y = self.visualRect(index).top()
        self._drag_item = item
        self._drag_type = "folder"
        origin_index = self.indexOfTopLevelItem(item)
        self.takeTopLevelItem(origin_index)
        self._placeholder_folder = None
        self._placeholder_index = 0
        self._placeholder_top_level_index = origin_index
        self._placeholder_item = QTreeWidgetItem(self, [" "])
        self._placeholder_item.setData(0, _PLACEHOLDER_ROLE, True)
        self._placeholder_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
        self.insertTopLevelItem(origin_index, self._placeholder_item)
        self._update_drop_line(y=initial_line_y)
        mime = QMimeData()
        mime.setData(_MIME_FOLDER_ID, str(folder_id).encode("utf-8"))
        drag = QDrag(self)
        drag.setMimeData(mime)
        if not pixmap.isNull():
            drag.setPixmap(pixmap)
            drag.setHotSpot(pixmap.rect().center())
        drag.exec(Qt.DropAction.MoveAction)
        self._cleanup_after_drag()

    def _cleanup_after_drag(self) -> None:
        if self._placeholder_item:
            p = self._placeholder_item.parent()
            if p:
                p.removeChild(self._placeholder_item)
            else:
                idx = self.indexOfTopLevelItem(self._placeholder_item)
                if idx >= 0:
                    self.takeTopLevelItem(idx)
            self._placeholder_item = None
        self._drag_item = None
        self._drag_type = ""
        self._dragged_folder_expanded = None
        self._folder_pressed = None
        self._did_drag = False
        self._placeholder_folder = None
        self._placeholder_top_level_index = -1
        if self.onDragEnded:
            self.onDragEnded()

    def _remove_placeholder(self) -> None:
        if self._placeholder_item:
            p = self._placeholder_item.parent()
            if p:
                p.removeChild(self._placeholder_item)
            else:
                idx = self.indexOfTopLevelItem(self._placeholder_item)
                if idx >= 0:
                    self.takeTopLevelItem(idx)
            self._placeholder_item = None
        self._drop_line.hide()

    def _update_drop_line(self, y: int | None = None) -> None:
        """Position and show the drop indicator line. If y is given, use it; else use placeholder's rect."""
        if y is not None:
            self._drop_line.setGeometry(0, y, self.viewport().width(), 3)
            self._drop_line.show()
            self._drop_line.raise_()
            return
        if not self._placeholder_item:
            self._drop_line.hide()
            return
        index = self.indexFromItem(self._placeholder_item, 0)
        rect = self.visualRect(index)
        self._drop_line.setGeometry(0, rect.top(), self.viewport().width(), 3)
        self._drop_line.show()
        self._drop_line.raise_()

    def dragEnterEvent(self, event) -> None:
        mime = event.mimeData()
        if mime.hasFormat(_MIME_SETLIST_ID) or mime.hasFormat(_MIME_FOLDER_ID):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:
        mime = event.mimeData()
        has_setlist = mime.hasFormat(_MIME_SETLIST_ID)
        has_folder = mime.hasFormat(_MIME_FOLDER_ID)
        if (not has_setlist and not has_folder) or not self._drag_item:
            event.ignore()
            return
        event.acceptProposedAction()
        pos = self.viewport().mapFrom(self, event.position().toPoint())
        item = self.itemAt(pos)
        if has_folder and self._drag_type == "folder":
            if item and item.data(0, _PLACEHOLDER_ROLE):
                return
            self._drag_move_folder(item, pos)
        else:
            if not item:
                self._drop_line.hide()
                return
            if item.data(0, _PLACEHOLDER_ROLE):
                return
            self._drag_move_setlist(item, pos)

    def _drag_move_folder(self, item: QTreeWidgetItem | None, pos: QPoint) -> None:
        if item is not None and item.parent() is not None:
            item = item.parent()
        if item is None:
            n = self.topLevelItemCount()
            target_index = max(0, n - 1) if n else 0
            if n > 0:
                last = self.topLevelItem(n - 1)
                idx = self.indexFromItem(last, 0)
                rect = self.visualRect(idx)
                line_y = rect.bottom()
            else:
                line_y = 0
        else:
            idx = self.indexOfTopLevelItem(item)
            index = self.indexFromItem(item, 0)
            rect = self.visualRect(index)
            if item.data(0, Qt.ItemDataRole.UserRole) is None:
                target_index = idx
                line_y = rect.top()
            elif pos.y() > rect.center().y():
                target_index = idx + 1
                line_y = rect.bottom()
            else:
                target_index = idx
                line_y = rect.top()
        self._update_drop_line(y=line_y)
        if target_index == self._placeholder_top_level_index:
            return
        self._remove_placeholder()
        self._placeholder_item = QTreeWidgetItem(self, [" "])
        self._placeholder_item.setData(0, _PLACEHOLDER_ROLE, True)
        self._placeholder_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
        self.insertTopLevelItem(target_index, self._placeholder_item)
        self._placeholder_folder = None
        self._placeholder_index = 0
        self._placeholder_top_level_index = target_index

    def _drag_move_setlist(self, item: QTreeWidgetItem, pos: QPoint) -> None:
        target_folder: QTreeWidgetItem
        target_index: int
        line_y: int
        if item.data(0, _TYPE_ROLE) == "folder":
            target_folder = item
            target_index = item.childCount()
            index = self.indexFromItem(item, 0)
            rect = self.visualRect(index)
            line_y = rect.bottom()
        else:
            parent = item.parent()
            if not parent:
                return
            index = self.indexFromItem(item, 0)
            rect = self.visualRect(index)
            if pos.y() > rect.center().y():
                target_index = parent.indexOfChild(item) + 1
                line_y = rect.bottom()
            else:
                target_index = parent.indexOfChild(item)
                line_y = rect.top()
            target_folder = parent
        self._update_drop_line(y=line_y)
        if target_folder == self._placeholder_folder and target_index == self._placeholder_index:
            return
        self._remove_placeholder()
        self._placeholder_item = QTreeWidgetItem(target_folder, [" "])
        self._placeholder_item.setData(0, _PLACEHOLDER_ROLE, True)
        self._placeholder_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
        target_folder.insertChild(target_index, self._placeholder_item)
        self._placeholder_folder = target_folder
        self._placeholder_index = target_index

    def dropEvent(self, event) -> None:
        mime = event.mimeData()
        if mime.hasFormat(_MIME_FOLDER_ID):
            self._drop_folder(event)
        elif mime.hasFormat(_MIME_SETLIST_ID):
            self._drop_setlist(event)
        else:
            event.ignore()

    def _drop_folder(self, event) -> None:
        mime = event.mimeData()
        try:
            dragged_id = int(mime.data(_MIME_FOLDER_ID).data().decode("utf-8"))
        except (ValueError, AttributeError):
            event.ignore()
            return
        event.accept()
        if not self.folderMoved:
            self._remove_placeholder()
            return
        ids_without_dragged: list[int] = []
        for i in range(self.topLevelItemCount()):
            top = self.topLevelItem(i)
            if top.data(0, _PLACEHOLDER_ROLE):
                continue
            fid = top.data(0, Qt.ItemDataRole.UserRole)
            if fid is not None and fid != dragged_id:
                ids_without_dragged.append(fid)
        self._remove_placeholder()
        drop_index = self._placeholder_top_level_index
        if drop_index >= 0 and drop_index <= len(ids_without_dragged):
            ids = ids_without_dragged[:drop_index] + [dragged_id] + ids_without_dragged[drop_index:]
        else:
            ids = ids_without_dragged + [dragged_id]
        if ids:
            self.folderMoved(ids, dragged_id, self._dragged_folder_expanded)

    def _drop_setlist(self, event) -> None:
        mime = event.mimeData()
        try:
            setlist_id = int(mime.data(_MIME_SETLIST_ID).data().decode("utf-8"))
        except (ValueError, AttributeError):
            event.ignore()
            return
        event.accept()
        target_folder_id: int | None = None
        target_sort_order = 0
        if self._placeholder_item and self._placeholder_folder is not None:
            target_folder_id = self._placeholder_folder.data(0, Qt.ItemDataRole.UserRole)
            target_sort_order = self._placeholder_index
        self._remove_placeholder()
        if self.setlistMoved:
            self.setlistMoved(setlist_id, target_folder_id, target_sort_order)


class SetlistSongsTable(QTableWidget):
    """Table with vertical-only drag-drop. Rows move visually during drag. Aligned with PlaylistTable pattern."""

    rowReordered = None  # Set by parent: callable() -> None, persists current order
    createActionsWidget = None  # Set by parent: callable(setlist_item_id: int) -> QWidget

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        self.setDragDropOverwriteMode(False)
        self.setDefaultDropAction(Qt.DropAction.CopyAction)
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
        # Use CopyAction so Qt does not remove source rows; we move them ourselves in dragMoveEvent.
        drag.exec(Qt.DropAction.CopyAction)
        self._drag_row = -1

    def _move_row_visually(self, from_row: int, to_row: int) -> None:
        """Move a row in the table. Recreate Actions widget to avoid Qt crash when moving cell widgets."""
        if from_row == to_row or from_row < 0 or to_row < 0:
            return
        n = self.rowCount()
        if from_row >= n or to_row > n:
            return
        items = [self.takeItem(from_row, c) for c in range(self.columnCount())]
        setlist_item_id = None
        if items[2]:
            setlist_item_id = items[2].data(Qt.ItemDataRole.UserRole)
        self.removeRow(from_row)  # Destroys cell widget; we recreate it below
        if to_row > from_row:
            to_row -= 1
        self.insertRow(to_row)
        for c, it in enumerate(items):
            if c != 6:
                self.setItem(to_row, c, it)
        if self.createActionsWidget and setlist_item_id is not None and isinstance(setlist_item_id, int):
            self.setCellWidget(to_row, 6, self.createActionsWidget(setlist_item_id))
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
        event.acceptProposedAction()
        event.setDropAction(Qt.DropAction.CopyAction)
        # Defer persist so Qt can finish drag-drop cleanup first (avoids native crash with cell widgets).
        if self.rowReordered:
            QTimer.singleShot(0, self.rowReordered)


class SetlistsView(QWidget):
    def __init__(
        self,
        app_state: AppState,
        playback_state=None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.app_state = app_state
        self.playback_state = playback_state
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
        self._splitter_restore_retries = 0
        self._songs_header_save_timer = QTimer(self)
        self._songs_header_save_timer.setSingleShot(True)
        self._songs_header_save_timer.timeout.connect(self._save_songs_table_header_state)
        self._top_split_save_timer = QTimer(self)
        self._top_split_save_timer.setSingleShot(True)
        self._top_split_save_timer.timeout.connect(lambda: set_setlists_top_split_state(self.top_split.sizes()))

        root = QVBoxLayout(self)

        btn_row = QHBoxLayout()
        add_setlist_btn = QPushButton("Add setlist")
        add_setlist_btn.clicked.connect(self._add_setlist)
        fm = add_setlist_btn.fontMetrics()
        add_setlist_btn.setFixedWidth(fm.horizontalAdvance("Add setlist") + 24)
        btn_row.addWidget(add_setlist_btn)
        self.copy_setlist_menu_btn = QToolButton()
        self.copy_setlist_menu_btn.setText("Copy...")
        self.copy_setlist_menu_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.copy_setlist_menu_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._copy_setlist_menu = QMenu(self)
        self.copy_setlist_menu_btn.setMenu(self._copy_setlist_menu)
        self.copy_setlist_menu_btn.setFixedHeight(add_setlist_btn.sizeHint().height())
        self.copy_setlist_menu_btn.setFixedWidth(fm.horizontalAdvance("Copy...") + 36)
        self._copy_setlist_menu.aboutToShow.connect(self._on_toolbar_copy_menu_about_to_show)
        self.copy_setlist_menu_btn.setEnabled(False)
        btn_row.addWidget(self.copy_setlist_menu_btn)
        add_folder_btn = QPushButton("Add folder")
        add_folder_btn.clicked.connect(self._add_folder)
        add_folder_btn.setFixedWidth(fm.horizontalAdvance("Add folder") + 24)
        btn_row.addWidget(add_folder_btn)
        import_abcp_btn = QPushButton("Import ABCP")
        import_abcp_btn.clicked.connect(self._import_abcp)
        import_abcp_btn.setFixedWidth(fm.horizontalAdvance("Import ABCP") + 24)
        btn_row.addWidget(import_abcp_btn)
        btn_row.addStretch()
        root.addLayout(btn_row)

        self.setlists_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.setlist_tree = SetlistTreeWidget()
        self.setlist_tree.setColumnCount(1)
        self.setlist_tree.setHeaderHidden(True)
        self.setlist_tree.setWordWrap(True)
        self.setlist_tree.setMinimumWidth(120)
        self.setlist_tree.setMaximumWidth(320)
        tree_font = self.setlist_tree.font()
        tree_font.setPointSize(tree_font.pointSize() + 2)
        self.setlist_tree.setFont(tree_font)
        self.setlist_tree.setItemDelegate(SetlistTreeDelegate(self.setlist_tree))
        self.setlist_tree.setUniformRowHeights(False)
        self.setlist_tree.setDragEnabled(True)
        self.setlist_tree.setAcceptDrops(True)
        self.setlist_tree.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        self.setlist_tree.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setlist_tree.setDropIndicatorShown(True)
        self.setlist_tree.setlistMoved = self._on_setlist_moved
        self.setlist_tree.folderMoved = self._on_folder_moved
        self.setlist_tree.onFolderDragStart = self._save_folder_expanded_state
        self.setlist_tree.onDragEnded = self._refresh_setlist_tree
        self.setlist_tree.currentItemChanged.connect(self._on_setlist_selected)
        self.setlist_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.setlist_tree.customContextMenuRequested.connect(self._on_setlist_tree_context_menu)
        self.setlist_tree.itemExpanded.connect(self._save_folder_expanded_state)
        self.setlist_tree.itemCollapsed.connect(self._save_folder_expanded_state)
        self.setlists_splitter.addWidget(self.setlist_tree)

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
        self.export_btn = QPushButton("Export")
        self.export_btn.setFixedWidth(self.export_btn.fontMetrics().horizontalAdvance("Export") + 24)
        self.export_btn.clicked.connect(self._export_set)
        btn_row.addWidget(self.save_btn)
        btn_row.addWidget(self.delete_btn)
        btn_row.addWidget(self.export_btn)
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
        self.songs_table.setColumnCount(7)
        self.songs_table.setHorizontalHeaderLabels(["", "", "Title", "Parts", "Duration", "Artist", "Actions"])
        self.songs_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.songs_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.songs_table.cellClicked.connect(self._on_song_cell_clicked)
        for col in range(7):
            self.songs_table.horizontalHeader().setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
        self.songs_table.horizontalHeader().setMinimumSectionSize(20)
        self.songs_table.horizontalHeader().resizeSection(0, 28)  # Play
        self.songs_table.horizontalHeader().resizeSection(1, 24)  # Flag
        fm = self.songs_table.fontMetrics()
        row_height = fm.lineSpacing() + 8
        self.songs_table.verticalHeader().setDefaultSectionSize(row_height)
        self.songs_table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self.songs_table.verticalHeader().setSectionsMovable(False)
        self.songs_table.verticalHeader().setSectionsClickable(True)
        self.songs_table.rowReordered = self._on_song_row_dragged
        self.songs_table.createActionsWidget = self._create_actions_widget
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
        self.assignment_panel.setlist_item_updated.connect(self._on_setlist_item_updated)

        self.editor_splitter = QSplitter(Qt.Orientation.Vertical)
        self.editor_splitter.addWidget(self.top_split)
        self.editor_splitter.addWidget(self.assignment_panel)
        self.editor_splitter.setStretchFactor(0, 1)
        self.editor_splitter.setStretchFactor(1, 2)
        editor_layout.addWidget(self.editor_splitter)

        self.setlists_splitter.addWidget(editor)
        self.setlists_splitter.setStretchFactor(1, 1)
        root.addWidget(self.setlists_splitter)

        self._setlists_splitter_save_timer = QTimer(self)
        self._setlists_splitter_save_timer.setSingleShot(True)
        self._setlists_splitter_save_timer.timeout.connect(
            lambda: set_setlists_splitter_state(self.setlists_splitter.sizes())
        )
        self.setlists_splitter.splitterMoved.connect(lambda: self._setlists_splitter_save_timer.start(150))
        self._editor_splitter_save_timer = QTimer(self)
        self._editor_splitter_save_timer.setSingleShot(True)
        self._editor_splitter_save_timer.timeout.connect(
            lambda: set_setlists_editor_splitter_state(self.editor_splitter.sizes())
        )
        self.editor_splitter.splitterMoved.connect(lambda: self._editor_splitter_save_timer.start(150))

        self._editor_enabled = False
        self._set_editor_enabled(False)
        self._pending_select_setlist_id: int | None = None

    def _set_editor_enabled(self, on: bool) -> None:
        self._editor_enabled = on
        for w in (
            self.save_btn,
            self.delete_btn,
            self.export_btn,
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
        if not self._splitter_restored:
            # Defer until after splitters are restored (avoids wrong layout)
            self._pending_select_setlist_id = setlist_id
            return
        self._refresh_setlist_tree()
        item = self._find_setlist_item(setlist_id)
        if item:
            parent = item.parent()
            if parent:
                parent.setExpanded(True)
            self.setlist_tree.setCurrentItem(item)
            self.setlist_tree.scrollToItem(item)

    def _save_folder_expanded_state(self) -> None:
        expanded = []
        for i in range(self.setlist_tree.topLevelItemCount()):
            top = self.setlist_tree.topLevelItem(i)
            if top.isExpanded():
                fid = top.data(0, Qt.ItemDataRole.UserRole)
                if fid is not None:
                    expanded.append(fid)
        set_setlists_folder_expanded_state(expanded)

    def _on_setlist_moved(self, setlist_id: int, target_folder_id: int | None, target_sort_order: int) -> None:
        """Handle drag-drop: move setlist to folder at position."""
        move_setlist_to_folder(self.app_state.conn, setlist_id, target_folder_id, target_sort_order)
        self.select_setlist_by_id(setlist_id)

    def _on_folder_moved(
        self,
        folder_ids_in_order: list[int],
        dragged_id: int,
        dragged_folder_expanded: bool | None,
    ) -> None:
        """Handle drag-drop: reorder folders."""
        if dragged_folder_expanded is not None:
            expanded = list(get_setlists_folder_expanded_state())
            if dragged_folder_expanded:
                if dragged_id not in expanded:
                    expanded.append(dragged_id)
            else:
                expanded = [x for x in expanded if x != dragged_id]
            set_setlists_folder_expanded_state(expanded)
        reorder_folders(self.app_state.conn, folder_ids_in_order)

    def _find_setlist_item(self, setlist_id: int) -> QTreeWidgetItem | None:
        """Find tree item for setlist by id. Returns None if not found."""
        root = self.setlist_tree.invisibleRootItem()
        for i in range(root.childCount()):
            folder_item = root.child(i)
            for j in range(folder_item.childCount()):
                child = folder_item.child(j)
                if child.data(0, _TYPE_ROLE) == "setlist" and child.data(0, Qt.ItemDataRole.UserRole) == setlist_id:
                    return child
        return None

    def _find_first_setlist_item(self) -> QTreeWidgetItem | None:
        """Find first setlist item in tree order. Returns None if no setlists."""
        root = self.setlist_tree.invisibleRootItem()
        for i in range(root.childCount()):
            folder_item = root.child(i)
            for j in range(folder_item.childCount()):
                child = folder_item.child(j)
                if child.data(0, _TYPE_ROLE) == "setlist":
                    return child
        return None

    def _refresh_setlist_tree(self) -> None:
        cur_id = None
        cur = self.setlist_tree.currentItem()
        if cur and cur.data(0, _TYPE_ROLE) == "setlist":
            cur_id = cur.data(0, Qt.ItemDataRole.UserRole)
        self.setlist_tree.blockSignals(True)
        self.setlist_tree.clear()
        grouped = list_setlists_grouped_by_folder(self.app_state.conn)
        for folder_or_none, setlists in grouped:
            if folder_or_none:
                folder_item = QTreeWidgetItem(self.setlist_tree, [folder_or_none.name])
                folder_item.setData(0, Qt.ItemDataRole.UserRole, folder_or_none.id)
                folder_item.setData(0, _TYPE_ROLE, "folder")
                for s in setlists:
                    child = QTreeWidgetItem(folder_item, [_fmt_setlist_display(s)])
                    child.setData(0, Qt.ItemDataRole.UserRole, s.id)
                    child.setData(0, _TYPE_ROLE, "setlist")
            else:
                folder_item = QTreeWidgetItem(self.setlist_tree, ["Uncategorized"])
                folder_item.setData(0, Qt.ItemDataRole.UserRole, None)
                folder_item.setData(0, _TYPE_ROLE, "folder")
                for s in setlists:
                    child = QTreeWidgetItem(folder_item, [_fmt_setlist_display(s)])
                    child.setData(0, Qt.ItemDataRole.UserRole, s.id)
                    child.setData(0, _TYPE_ROLE, "setlist")
        if cur_id is not None:
            item = self._find_setlist_item(cur_id)
            if item:
                self.setlist_tree.setCurrentItem(item)
                parent = item.parent()
                if parent:
                    parent.setExpanded(True)
            else:
                cur_id = None
        if cur_id is None:
            first_setlist = self._find_first_setlist_item()
            if first_setlist:
                parent = first_setlist.parent()
                if parent:
                    parent.setExpanded(True)
                self.setlist_tree.setCurrentItem(first_setlist)
        expanded_ids = get_setlists_folder_expanded_state()
        for i in range(self.setlist_tree.topLevelItemCount()):
            top = self.setlist_tree.topLevelItem(i)
            fid = top.data(0, Qt.ItemDataRole.UserRole)
            if fid is not None and fid in expanded_ids:
                top.setExpanded(True)
            elif fid is None:
                top.setExpanded(True)
            else:
                top.setExpanded(False)
        self.setlist_tree.blockSignals(False)
        self._on_setlist_selected(self.setlist_tree.currentItem(), None)

    def _on_setlist_selected(self, current: QTreeWidgetItem | None, previous: QTreeWidgetItem | None) -> None:
        # When switching away from a setlist with unsaved changes, confirm first
        if previous is not None and previous.data(0, _TYPE_ROLE) == "setlist":
            is_switching = current is None or current.data(0, _TYPE_ROLE) != "setlist" or current.data(0, Qt.ItemDataRole.UserRole) != previous.data(0, Qt.ItemDataRole.UserRole)
            if is_switching and self.has_unsaved_changes():
                reply = QMessageBox.question(
                    self,
                    "Unsaved changes",
                    "You have unsaved changes. Are you sure you want to leave?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                if reply != QMessageBox.StandardButton.Yes:
                    self.setlist_tree.blockSignals(True)
                    self.setlist_tree.setCurrentItem(previous)
                    self.setlist_tree.blockSignals(False)
                    return
        if current is None or current.data(0, _TYPE_ROLE) != "setlist":
            self._selected_setlist_id = None
            self.copy_setlist_menu_btn.setEnabled(False)
            self._set_editor_enabled(False)
            self._update_duration_computed()
            return
        sid = current.data(0, Qt.ItemDataRole.UserRole)
        self._selected_setlist_id = sid
        s = next(x for x in list_setlists(self.app_state.conn) if x.id == sid)
        self.copy_setlist_menu_btn.setEnabled(True)
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
        for layout_id, _layout_name, band_name in list_all_band_layouts(self.app_state.conn):
            self.band_layout_combo.addItem(band_name, layout_id)
        self.band_layout_combo.blockSignals(False)

    def _on_band_layout_combo_changed(self) -> None:
        self._refresh_songs_table()
        self._refresh_assignment_panel()

    def _refresh_songs_table(self, select_item_id: int | None = None) -> None:
        if self._filling_songs:
            QTimer.singleShot(0, lambda s=select_item_id: self._refresh_songs_table(select_item_id=s))
            return
        if not self._selected_setlist_id:
            self.songs_table.setRowCount(0)
            self.songs_table.repaint()
            self.export_btn.setEnabled(False)
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
            play_item = QTableWidgetItem("▶")
            play_item.setFlags(play_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            play_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.songs_table.setItem(i, 0, play_item)

            err = self._song_has_error(sl, r, bulk, slots)
            flag = QTableWidgetItem("\u26a0" if err else "")
            flag.setForeground(QColor("#ff4444") if err else QColor(COLOR_ON_SURFACE))
            f = QFont()
            f.setPointSize(f.pointSize() + 4)
            f.setWeight(QFont.Weight.Bold)
            flag.setFont(f)
            flag.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            flag.setFlags(flag.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.songs_table.setItem(i, 1, flag)

            t = QTableWidgetItem(r.title)
            t.setData(Qt.ItemDataRole.UserRole, r.item.id)
            t.setFlags(t.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.songs_table.setItem(i, 2, t)

            pc = QTableWidgetItem(str(r.part_count))
            pc.setFlags(pc.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.songs_table.setItem(i, 3, pc)

            dur = QTableWidgetItem(_fmt_duration(r.duration_seconds))
            dur.setFlags(dur.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.songs_table.setItem(i, 4, dur)

            art = QTableWidgetItem(r.composers or "—")
            art.setFlags(art.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.songs_table.setItem(i, 5, art)

            self.songs_table.setCellWidget(i, 6, self._create_actions_widget(r.item.id))

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
            self.songs_table.repaint()
        self.export_btn.setEnabled(len(rows) > 0)
        self._update_duration_computed()

    def _create_actions_widget(self, setlist_item_id: int) -> QWidget:
        """Create Actions column widget (up/down/remove) for a setlist item. Used by table refresh and drag-move."""
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(2, 0, 2, 0)
        _btn_style = "padding: 0 4px; font-size: 11px; min-height: 0;"
        fm = self.songs_table.fontMetrics()
        up_btn = QPushButton("\u2191")
        up_btn.setStyleSheet(_btn_style)
        up_btn.setFixedWidth(fm.horizontalAdvance("\u2191") + 8)
        up_btn.setFixedHeight(18)
        up_btn.clicked.connect(lambda checked=False, iid=setlist_item_id: self._move_song(iid, -1))
        down_btn = QPushButton("\u2193")
        down_btn.setStyleSheet(_btn_style)
        down_btn.setFixedWidth(fm.horizontalAdvance("\u2193") + 8)
        down_btn.setFixedHeight(18)
        down_btn.clicked.connect(lambda checked=False, iid=setlist_item_id: self._move_song(iid, 1))
        rem_btn = QPushButton("Remove")
        rem_btn.setStyleSheet(_btn_style)
        rem_btn.setFixedWidth(fm.horizontalAdvance("Remove") + 12)
        rem_btn.setFixedHeight(18)
        rem_btn.clicked.connect(lambda checked=False, iid=setlist_item_id: self._remove_item(iid))
        h.addWidget(up_btn)
        h.addWidget(down_btn)
        h.addWidget(rem_btn)
        return w

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
        # Warning: song has no band layout (song_layout) for the setlist's band
        if r.item.song_layout_id is None:
            return True
        overrides = get_setlist_band_assignments(self.app_state.conn, r.item.id)
        layout = {
            a.player_id: a.part_number
            for a in get_song_layout_assignments(self.app_state.conn, r.item.song_layout_id)
        }
        parts = json.loads(r.parts_json) if r.parts_json else []
        pbn = {int(p["part_number"]): p for p in parts}
        assigned_parts: set[int] = set()
        for s in slots:
            pid = s.player_id
            pn = overrides[pid] if pid in overrides else layout.get(pid)
            if pn is None:
                continue
            assigned_parts.add(pn)
            pm = pbn.get(pn)
            if not pm:
                continue
            iid = pm.get("instrument_id")
            if iid:
                equiv_ids = get_instrument_ids_with_same_name_ci(self.app_state.conn, iid)
                if not (equiv_ids and (bulk.get(pid, set()) & equiv_ids)):
                    return True
        # Warning: song has band layout but has unassigned parts (other than none)
        for p in parts:
            try:
                pnum = int(p.get("part_number"))
            except (TypeError, ValueError):
                continue
            if pnum not in assigned_parts:
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

    def _on_song_cell_clicked(self, row: int, col: int) -> None:
        if col == 0 and self.playback_state and self._selected_setlist_id:
            self._play_from_setlist(row)

    def _play_from_setlist(self, start_index: int) -> None:
        """Load setlist into playlist, start from start_index, use setlist band layout."""
        if not self.playback_state or not self._selected_setlist_id:
            return
        rows = list_setlist_items_with_song_meta(self.app_state.conn, self._selected_setlist_id)
        sl = next(s for s in list_setlists(self.app_state.conn) if s.id == self._selected_setlist_id)
        entries = []
        for r in rows:
            fp = get_primary_file_path_for_song(self.app_state.conn, r.item.song_id)
            if fp:
                fp = resolve_music_path(fp) or fp
                song_layout_id = r.item.song_layout_id
                if sl.band_layout_id and song_layout_id is None:
                    song_layout_id = get_or_create_song_layout_for_band(
                        self.app_state.conn, r.item.song_id, sl.band_layout_id
                    )
                    update_setlist_item(self.app_state.conn, r.item.id, song_layout_id=song_layout_id)
                entries.append(
                    PlaylistEntry(
                        song_id=r.item.song_id,
                        file_path=fp,
                        title=r.title,
                        source="setlist",
                        song_layout_id=song_layout_id,
                        band_layout_id=sl.band_layout_id,
                        setlist_item_id=r.item.id,
                    )
                )
        if not entries:
            return
        for e in entries:
            if sl.band_layout_id and e.song_layout_id:
                update_song_last_layout(
                    self.app_state.conn, e.song_id, sl.band_layout_id, e.song_layout_id, e.setlist_item_id
                )
        self.playback_state.active_band_layout_id = sl.band_layout_id
        self.playback_state.replace_playlist(entries, start_index=start_index)

    def _on_song_row_dragged(self) -> None:
        """Persist current table order after drag-drop. Table is already correct visually; just save and update side panels."""
        if self._filling_songs or not self._selected_setlist_id:
            return
        ids: list[int] = []
        for r in range(self.songs_table.rowCount()):
            it = self.songs_table.item(r, 2)
            if it:
                val = it.data(Qt.ItemDataRole.UserRole)
                if val is not None and isinstance(val, int):
                    ids.append(val)
        if len(ids) != self.songs_table.rowCount():
            return
        reorder_setlist_items(self.app_state.conn, self._selected_setlist_id, ids)
        self._refresh_assignment_panel()
        self._update_duration_computed()

    def _on_song_selection_changed(self) -> None:
        self._refresh_assignment_panel()

    def _on_assignment_changed(self) -> None:
        self._refresh_assignment_panel()
        self._refresh_error_column_only()

    def _on_setlist_item_updated(self, setlist_item_id: int) -> None:
        """When setlist band assignment changes, restart playback if it's the active item."""
        if self.playback_state and self.playback_state.get_active_setlist_item_id() == setlist_item_id:
            self.playback_state.restart_current_with_new_stereo()

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
            flag = self.songs_table.item(i, 1)
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
        folder_id: int | None = None
        cur = self.setlist_tree.currentItem()
        if cur:
            if cur.data(0, _TYPE_ROLE) == "folder":
                folder_id = cur.data(0, Qt.ItemDataRole.UserRole)
            elif cur.data(0, _TYPE_ROLE) == "setlist":
                parent = cur.parent()
                folder_id = parent.data(0, Qt.ItemDataRole.UserRole) if parent else None
        bands = list_setlists(self.app_state.conn)
        n = sum(1 for b in bands if b.name.startswith("New setlist"))
        name = f"New setlist {n + 1}"
        new_id = add_setlist(self.app_state.conn, name, folder_id=folder_id)
        self.select_setlist_by_id(new_id)

    def _add_folder(self) -> None:
        name, ok = QInputDialog.getText(self, "Add folder", "Folder name:")
        if not ok or not name.strip():
            return
        add_folder(self.app_state.conn, name.strip())
        self._refresh_setlist_tree()

    def _add_setlist_in_folder(self, folder_id: int | None) -> None:
        """Create a new set in the given folder (or uncategorized if None)."""
        bands = list_setlists(self.app_state.conn)
        n = sum(1 for b in bands if b.name.startswith("New setlist"))
        name = f"New setlist {n + 1}"
        new_id = add_setlist(self.app_state.conn, name, folder_id=folder_id)
        self.select_setlist_by_id(new_id)

    def _export_set(self) -> None:
        """Export the currently selected setlist (toolbar button)."""
        if not self._selected_setlist_id:
            return
        self._open_export_dialog(self._selected_setlist_id)

    def _import_abcp(self) -> None:
        """Import an ABCP file as a new setlist."""
        start = get_set_export_dir() or str(Path.home())
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import ABCP",
            start,
            "ABCP Playlist (*.abcp);;All Files (*)",
        )
        if not path:
            return
        path_obj = Path(path)
        try:
            track_paths = parse_abcp(path_obj)
        except ValueError as e:
            QMessageBox.critical(
                self,
                "Import ABCP",
                f"Could not read ABCP file:\n{e}",
            )
            return
        if not track_paths:
            QMessageBox.information(
                self,
                "Import ABCP",
                "The file contains no tracks.",
            )
            return
        conn = self.app_state.conn
        matched: list[tuple[int, int]] = []  # (position, song_id)
        unmatched: list[str] = []
        for pos, file_path in enumerate(track_paths):
            song_id = get_song_id_for_file_path(conn, file_path)
            if song_id is not None:
                matched.append((pos, song_id))
            else:
                unmatched.append(file_path)
        if not matched:
            QMessageBox.warning(
                self,
                "Import ABCP",
                "None of the tracks in the file were found in your library. "
                "Paths must match exactly.",
            )
            return
        if unmatched:
            reply = QMessageBox.question(
                self,
                "Import ABCP",
                f"{len(matched)} of {len(track_paths)} tracks matched. "
                f"{len(unmatched)} path(s) not found in library.\n\n"
                "Import the matched tracks only?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        setlist_name = path_obj.stem
        setlist_id = add_setlist(self.app_state.conn, setlist_name)
        for pos, song_id in matched:
            add_setlist_item(
                self.app_state.conn,
                setlist_id,
                song_id,
                position=pos,
            )
        self._refresh_setlist_tree()
        self.select_setlist_by_id(setlist_id)
        QMessageBox.information(
            self,
            "Import ABCP",
            f"Imported {len(matched)} tracks into setlist '{setlist_name}'.",
        )

    def _export_to_abcp(self, setlist_id: int) -> None:
        """Export setlist to ABCP file."""
        setlists = {s.id: s for s in list_setlists(self.app_state.conn)}
        s = setlists.get(setlist_id)
        if not s:
            return
        items = list_setlist_items_with_song_meta(self.app_state.conn, setlist_id)
        if not items:
            QMessageBox.warning(
                self,
                "Export to ABCP",
                "This setlist has no songs to export.",
            )
            return
        reply = QMessageBox.question(
            self,
            "Export to ABCP",
            "ABCP files contain only track paths and song order. Band layout, "
            "part assignments, notes, timing, and other metadata will not be included. "
            "Exported files remain compatible with ABC Player.\n\nContinue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        conn = self.app_state.conn
        track_paths: list[str] = []
        skipped = 0
        for row in items:
            fp = get_primary_file_path_for_song(conn, row.item.song_id)
            if fp:
                track_paths.append(fp)
            else:
                skipped += 1
        if not track_paths:
            QMessageBox.warning(
                self,
                "Export to ABCP",
                "No songs have file paths; nothing to export.",
            )
            return
        start = get_set_export_dir() or str(Path.home())
        default_name = f"{s.name}.abcp"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export to ABCP",
            str(Path(start) / default_name),
            "ABCP Playlist (*.abcp);;All Files (*)",
        )
        if not path:
            return
        if not path.lower().endswith(".abcp"):
            path = path + ".abcp"
        try:
            write_abcp(Path(path), track_paths)
        except OSError as e:
            QMessageBox.critical(
                self,
                "Export to ABCP",
                f"Could not write file:\n{e}",
            )
            return
        msg = f"Exported {len(track_paths)} tracks to {Path(path).name}."
        if skipped:
            msg += f"\n\n{skipped} song(s) had no file path and were omitted."
        QMessageBox.information(self, "Export to ABCP", msg)

    def _on_toolbar_copy_menu_about_to_show(self) -> None:
        self._copy_setlist_menu.clear()
        sid = self._selected_setlist_id
        if sid is None:
            return
        self._add_setlist_copy_actions(self._copy_setlist_menu, sid)

    def _add_setlist_copy_actions(self, menu: QMenu, current_setlist_id: int) -> None:
        cid = current_setlist_id
        menu.addAction("Copy Setlist as New").triggered.connect(lambda *_: self._on_copy_setlist_as_new(cid))
        menu.addAction("Prepend to setlist..").triggered.connect(lambda *_: self._on_prepend_current_to_other(cid))
        menu.addAction("Prepend from setlist...").triggered.connect(lambda *_: self._on_prepend_other_into_current(cid))
        menu.addAction("Append to setlist...").triggered.connect(lambda *_: self._on_append_current_to_other(cid))
        menu.addAction("Append from setlist...").triggered.connect(lambda *_: self._on_append_other_into_current(cid))

    def _pick_other_setlist(self, exclude_id: int, title: str, label: str) -> int | None:
        all_setlists = list_setlists(self.app_state.conn)
        others = [
            (s, len(list_setlist_items(self.app_state.conn, s.id)))
            for s in all_setlists
            if s.id != exclude_id
        ]
        if not others:
            QMessageBox.information(
                self,
                title,
                "No other setlists available. Create another setlist first.",
            )
            return None
        titles = [f"{s.name} ({n} songs)" for s, n in others]
        picked, ok = QInputDialog.getItem(self, title, label, titles, 0, False)
        if not ok or not picked:
            return None
        idx = titles.index(picked)
        return others[idx][0].id

    def _on_copy_setlist_as_new(self, source_setlist_id: int) -> None:
        try:
            new_id = duplicate_setlist(self.app_state.conn, source_setlist_id)
        except ValueError as e:
            QMessageBox.critical(self, "Copy Setlist", str(e))
            return
        self._refresh_setlist_tree()
        self.select_setlist_by_id(new_id)

    def _on_prepend_current_to_other(self, current_id: int) -> None:
        other_id = self._pick_other_setlist(
            current_id,
            "Prepend to setlist",
            "Select setlist to prepend to (current setlist will be copied to its beginning):",
        )
        if other_id is None:
            return
        self._merge_two_setlists(other_id, current_id, prepend=True)

    def _on_prepend_other_into_current(self, current_id: int) -> None:
        other_id = self._pick_other_setlist(
            current_id,
            "Prepend from setlist",
            "Select setlist to copy to the beginning of the current setlist:",
        )
        if other_id is None:
            return
        self._merge_two_setlists(current_id, other_id, prepend=True)

    def _on_append_current_to_other(self, current_id: int) -> None:
        other_id = self._pick_other_setlist(
            current_id,
            "Append to setlist",
            "Select setlist to append to (current setlist will be copied to its end):",
        )
        if other_id is None:
            return
        self._merge_two_setlists(other_id, current_id, prepend=False)

    def _on_append_other_into_current(self, current_id: int) -> None:
        other_id = self._pick_other_setlist(
            current_id,
            "Append from setlist",
            "Select setlist to copy to the end of the current setlist:",
        )
        if other_id is None:
            return
        self._merge_two_setlists(current_id, other_id, prepend=False)

    def _merge_two_setlists(self, target_setlist_id: int, source_setlist_id: int, prepend: bool) -> None:
        """Merge a copy of source songs into target (prepend or append). Only song order is copied."""
        if target_setlist_id == source_setlist_id:
            return
        all_setlists = list_setlists(self.app_state.conn)
        target = next((s for s in all_setlists if s.id == target_setlist_id), None)
        source_setlist = next((s for s in all_setlists if s.id == source_setlist_id), None)
        if not target or not source_setlist:
            return
        if not list_setlist_items(self.app_state.conn, source_setlist_id):
            QMessageBox.information(
                self,
                "Copy setlist",
                "The selected setlist has no songs.",
            )
            return
        try:
            added = merge_setlist_into(
                self.app_state.conn,
                target_setlist_id,
                source_setlist_id,
                prepend=prepend,
                copy_item_details=False,
            )
        except ValueError as e:
            QMessageBox.critical(self, "Copy setlist", str(e))
            return
        self._refresh_setlist_tree()
        if self._selected_setlist_id == target_setlist_id:
            cur = self.setlist_tree.currentItem()
            if cur:
                self._on_setlist_selected(cur, None)
            else:
                self._refresh_songs_table()
        action = "Prepended" if prepend else "Appended"
        QMessageBox.information(
            self,
            "Copy setlist",
            f"{action} {added} song(s) from '{source_setlist.name}' into '{target.name}'.",
        )

    def _open_export_dialog(self, setlist_id: int) -> None:
        """Open the set export dialog for the given setlist."""
        setlists = {s.id: s for s in list_setlists(self.app_state.conn)}
        s = setlists.get(setlist_id)
        if not s:
            return
        items = list_setlist_items_with_song_meta(self.app_state.conn, setlist_id)
        if not items:
            QMessageBox.warning(
                self,
                "Export Set",
                "This setlist has no songs to export.",
            )
            return
        dlg = SetExportDialog(
            self.app_state,
            setlist_id,
            s.name,
            s.band_layout_id,
            self,
        )
        dlg.exec()

    def _delete_setlist_by_id(self, setlist_id: int) -> None:
        """Delete a setlist by id. Used from context menu."""
        sets_list = list_setlists(self.app_state.conn)
        s = next((x for x in sets_list if x.id == setlist_id), None)
        if not s:
            return
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
            delete_setlist(self.app_state.conn, setlist_id)
            if self._selected_setlist_id == setlist_id:
                self._selected_setlist_id = None
                self._set_editor_enabled(False)
            self._refresh_setlist_tree()

    def _on_setlist_tree_context_menu(self, pos) -> None:
        item = self.setlist_tree.itemAt(pos)
        menu = QMenu(self)
        target_folder_id: int | None = None
        if item:
            if item.data(0, _TYPE_ROLE) == "folder":
                folder_id = item.data(0, Qt.ItemDataRole.UserRole)
                if folder_id is not None:
                    target_folder_id = folder_id
                    menu.addAction("Rename folder").triggered.connect(
                        lambda: self._rename_folder(folder_id)
                    )
                    menu.addAction("Delete folder").triggered.connect(
                        lambda: self._delete_folder(folder_id)
                    )
            elif item.data(0, _TYPE_ROLE) == "setlist":
                setlist_id = item.data(0, Qt.ItemDataRole.UserRole)
                if setlist_id is not None:
                    parent = item.parent()
                    target_folder_id = parent.data(0, Qt.ItemDataRole.UserRole) if parent else None
                    menu.addAction("Export set...").triggered.connect(
                        lambda: self._open_export_dialog(setlist_id)
                    )
                    menu.addAction("Export to ABCP...").triggered.connect(
                        lambda: self._export_to_abcp(setlist_id)
                    )
                    copy_submenu = menu.addMenu("Copy...")
                    self._add_setlist_copy_actions(copy_submenu, setlist_id)
                    menu.addAction("Delete set").triggered.connect(
                        lambda: self._delete_setlist_by_id(setlist_id)
                    )
        menu.addAction("New set").triggered.connect(
            lambda: self._add_setlist_in_folder(target_folder_id)
        )
        menu.addAction("Add folder").triggered.connect(self._add_folder)
        menu.exec(self.setlist_tree.viewport().mapToGlobal(pos))

    def _rename_folder(self, folder_id: int) -> None:
        folders = {f.id: f for f in list_folders(self.app_state.conn)}
        folder = folders.get(folder_id)
        if not folder:
            return
        name, ok = QInputDialog.getText(self, "Rename folder", "Folder name:", text=folder.name)
        if not ok or not name.strip():
            return
        update_folder(self.app_state.conn, folder_id, name=name.strip())
        self._refresh_setlist_tree()

    def _delete_folder(self, folder_id: int) -> None:
        try:
            delete_folder(self.app_state.conn, folder_id)
        except ValueError as e:
            QMessageBox.warning(self, "Cannot delete", str(e))
            return
        self._refresh_setlist_tree()

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
        self._refresh_setlist_tree()

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
            self._refresh_setlist_tree()
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

    def _remove_item(self, item_id: int) -> None:
        remove_setlist_item(self.app_state.conn, item_id)
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

    def _restore_setlists_splitters(self) -> None:
        """Restore splitter positions from preferences. Runs deferred so layout is ready."""
        total = self.setlists_splitter.width()
        total_h = self.setlists_splitter.height()
        if total < 200 or total_h < 150:
            # Geometry not ready yet; retry up to 20 times (≈1s total)
            if self._splitter_restore_retries < 20:
                self._splitter_restore_retries += 1
                QTimer.singleShot(50, self._restore_setlists_splitters)
            return
        if not self._splitter_restored:
            self._splitter_restored = True
            saved = get_setlists_splitter_state()
            if saved and len(saved) >= 2:
                left_saved, right_saved = saved[0], saved[1]
                total_saved = left_saved + right_saved
                if total_saved > 0 and left_saved >= 120:
                    ratio = left_saved / total_saved
                    left_now = int(total * ratio)
                    left_now = max(120, min(320, left_now))  # Clamp to tree min/max
                    self.setlists_splitter.setSizes([left_now, total - left_now])
                else:
                    left_d, right_d = DEFAULT_SETLISTS_SPLITTER_STATE[0], DEFAULT_SETLISTS_SPLITTER_STATE[1]
                    ratio = left_d / (left_d + right_d) if (left_d + right_d) > 0 else 0.17
                    left_now = max(120, min(320, int(total * ratio)))
                    self.setlists_splitter.setSizes([left_now, total - left_now])
            else:
                left_d, right_d = DEFAULT_SETLISTS_SPLITTER_STATE[0], DEFAULT_SETLISTS_SPLITTER_STATE[1]
                ratio = left_d / (left_d + right_d) if (left_d + right_d) > 0 else 0.17
                left_now = max(120, min(320, int(total * ratio)))
                self.setlists_splitter.setSizes([left_now, total - left_now])
        if not self._editor_splitter_restored:
            self._editor_splitter_restored = True
            total_ed = self.editor_splitter.height()
            if total_ed >= 150:
                saved = get_setlists_editor_splitter_state()
                if saved and len(saved) >= 2 and saved[0] >= 80 and saved[1] >= 80:
                    ratio_top = saved[0] / (saved[0] + saved[1])
                    top_now = int(total_ed * ratio_top)
                    top_now = max(80, min(total_ed - 80, top_now))
                    self.editor_splitter.setSizes([top_now, total_ed - top_now])
                else:
                    top_d, bot_d = DEFAULT_SETLISTS_EDITOR_SPLITTER_STATE[0], DEFAULT_SETLISTS_EDITOR_SPLITTER_STATE[1]
                    ratio_top = top_d / (top_d + bot_d) if (top_d + bot_d) > 0 else 0.48
                    top_now = max(80, min(total_ed - 80, int(total_ed * ratio_top)))
                    self.editor_splitter.setSizes([top_now, total_ed - top_now])
        if not self._top_split_restored:
            self._top_split_restored = True
            total_top = self.top_split.width()
            if total_top >= 200:
                saved = get_setlists_top_split_state()
                if saved and len(saved) >= 2 and saved[0] >= 80 and saved[1] >= 80:
                    ratio_left = saved[0] / (saved[0] + saved[1])
                    left_now = int(total_top * ratio_left)
                    left_now = max(80, min(total_top - 80, left_now))
                    self.top_split.setSizes([left_now, total_top - left_now])
                else:
                    left_d, right_d = DEFAULT_SETLISTS_TOP_SPLIT_STATE[0], DEFAULT_SETLISTS_TOP_SPLIT_STATE[1]
                    ratio_left = left_d / (left_d + right_d) if (left_d + right_d) > 0 else 0.33
                    left_now = max(80, min(total_top - 80, int(total_top * ratio_left)))
                    self.top_split.setSizes([left_now, total_top - left_now])
        if not self._songs_table_header_restored:
            self._songs_table_header_restored = True
            saved = get_setlists_songs_table_header_state()
            hh = self.songs_table.horizontalHeader()
            widths = saved if saved else DEFAULT_SETLISTS_SONGS_TABLE_HEADER_STATE
            for i, w in enumerate(widths):
                if i < hh.count():
                    hh.resizeSection(i, w)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        # Restore splitters first (deferred so layout is ready), then load data.
        # This prevents the folder/sets list from taking the entire screen.
        self._splitter_restore_retries = 0
        QTimer.singleShot(100, self._restore_setlists_splitters)
        QTimer.singleShot(150, self._on_show_deferred)

    def _on_show_deferred(self) -> None:
        """Called after showEvent so settings are restored before loading data."""
        self._refresh_setlist_tree()
        if self._pending_select_setlist_id is not None:
            sid = self._pending_select_setlist_id
            self._pending_select_setlist_id = None
            item = self._find_setlist_item(sid)
            if item:
                parent = item.parent()
                if parent:
                    parent.setExpanded(True)
                self.setlist_tree.setCurrentItem(item)
                self.setlist_tree.scrollToItem(item)
