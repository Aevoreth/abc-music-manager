"""Tree-structured setlist picker for Set Play and similar read-only selection UIs."""

from __future__ import annotations

import sqlite3

from PySide6.QtCore import Qt, QModelIndex, QTimer
from PySide6.QtGui import QMouseEvent, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import QComboBox, QTreeView

from ..db.setlist_repo import list_setlists_grouped_by_folder

_TYPE_ROLE = Qt.ItemDataRole.UserRole + 1
_MIN_VISIBLE_ROWS = 10
_MAX_VISIBLE_ROWS = 15


class SetlistPickerTreeView(QTreeView):
    """Tree view where clicking anywhere on a folder row toggles expand/collapse."""

    def __init__(self, combo: "SetlistPickerCombo") -> None:
        super().__init__(combo)
        self._combo = combo

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            index = self.indexAt(event.position().toPoint())
            if index.isValid() and index.data(_TYPE_ROLE) == "folder":
                # QComboBox closes its popup on mouse release whenever currentIndex is
                # valid (common on Windows styles / frozen builds). Suppress that so
                # expanding a folder does not dismiss the list.
                self._combo._suppress_hide_popup()
                self.setExpanded(index, not self.isExpanded(index))
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            index = self.indexAt(event.position().toPoint())
            if index.isValid() and index.data(_TYPE_ROLE) == "folder":
                event.accept()
                return
        super().mouseReleaseEvent(event)


class SetlistPickerCombo(QComboBox):
    """Combo box whose popup shows setlists grouped in collapsible folders."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._selected_id: int | None = None
        self._selected_text = "(select)"
        self._allow_hide_popup = True
        self._model = QStandardItemModel(self)
        self.setModel(self._model)
        tree = SetlistPickerTreeView(self)
        tree.setHeaderHidden(True)
        tree.setRootIsDecorated(True)
        tree.setExpandsOnDoubleClick(False)
        tree.setItemsExpandable(True)
        tree.setAllColumnsShowFocus(True)
        tree.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        tree.expanded.connect(self._on_tree_structure_changed)
        tree.collapsed.connect(self._on_tree_structure_changed)
        self.setView(tree)
        self.view().pressed.connect(self._on_view_pressed)

    def hidePopup(self) -> None:
        if not self._allow_hide_popup:
            return
        super().hidePopup()

    def _suppress_hide_popup(self) -> None:
        """Ignore hidePopup for the rest of this click (folder expand/collapse)."""
        self._allow_hide_popup = False
        QTimer.singleShot(0, self._restore_hide_popup)

    def _restore_hide_popup(self) -> None:
        self._allow_hide_popup = True

    def currentData(self, role: int = Qt.ItemDataRole.UserRole) -> object:
        if role == Qt.ItemDataRole.UserRole:
            return self._selected_id
        return super().currentData(role)

    def currentText(self) -> str:
        return self._selected_text

    def populate(self, conn: sqlite3.Connection, *, preserve_id: int | None = None) -> None:
        self.blockSignals(True)
        self._model.clear()
        placeholder = QStandardItem("(select)")
        placeholder.setData(None, Qt.ItemDataRole.UserRole)
        placeholder.setData("placeholder", _TYPE_ROLE)
        self._model.appendRow(placeholder)

        grouped = list_setlists_grouped_by_folder(conn)
        for folder_or_none, setlists in grouped:
            if folder_or_none:
                folder = QStandardItem(folder_or_none.name)
                folder.setData(folder_or_none.id, Qt.ItemDataRole.UserRole)
            else:
                folder = QStandardItem("Uncategorized")
                folder.setData(None, Qt.ItemDataRole.UserRole)
            folder.setData("folder", _TYPE_ROLE)
            folder.setSelectable(False)
            folder.setEditable(False)
            self._model.appendRow(folder)

            for s in setlists:
                label = s.name + (" [locked]" if s.locked else "")
                item = QStandardItem(label)
                item.setData(s.id, Qt.ItemDataRole.UserRole)
                item.setData("setlist", _TYPE_ROLE)
                folder.appendRow(item)

        for row in range(self._model.rowCount()):
            top = self._model.item(row)
            if top is not None and top.data(_TYPE_ROLE) == "folder":
                self.view().collapse(self._model.indexFromItem(top))

        if preserve_id is not None and self._select_setlist_id(preserve_id, expand_parent=True):
            pass
        else:
            self._select_placeholder()
        self.blockSignals(False)

    def _select_placeholder(self) -> None:
        self._selected_id = None
        self._selected_text = "(select)"
        self._set_current_row(self._model.item(0))

    def _select_setlist_id(self, setlist_id: int, *, expand_parent: bool) -> bool:
        item = self._find_setlist_item(setlist_id)
        if item is None:
            return False
        if expand_parent:
            parent = item.parent()
            if parent is not None:
                parent_index = self._model.indexFromItem(parent)
                self.view().expand(parent_index)
        self._apply_setlist_item(item)
        return True

    def _apply_setlist_item(self, item: QStandardItem) -> None:
        self._selected_id = item.data(Qt.ItemDataRole.UserRole)
        self._selected_text = item.text().replace(" [locked]", "")
        self._set_current_row(item)

    def _set_current_row(self, item: QStandardItem | None) -> None:
        if item is None:
            return
        index = self._model.indexFromItem(item)
        parent = item.parent()
        if parent is not None:
            self.setRootModelIndex(parent.index())
            self.setCurrentIndex(item.row())
        else:
            self.setRootModelIndex(QModelIndex())
            self.setCurrentIndex(item.row())
        self.setRootModelIndex(QModelIndex())

    def _find_setlist_item(self, setlist_id: int) -> QStandardItem | None:
        for row in range(self._model.rowCount()):
            top = self._model.item(row)
            if top is None:
                continue
            if top.data(_TYPE_ROLE) == "setlist" and top.data(Qt.ItemDataRole.UserRole) == setlist_id:
                return top
            if top.data(_TYPE_ROLE) != "folder":
                continue
            for child_row in range(top.rowCount()):
                child = top.child(child_row)
                if (
                    child is not None
                    and child.data(_TYPE_ROLE) == "setlist"
                    and child.data(Qt.ItemDataRole.UserRole) == setlist_id
                ):
                    return child
        return None

    def _on_view_pressed(self, index: QModelIndex) -> None:
        if not index.isValid():
            return
        item = self._model.itemFromIndex(index)
        if item is None:
            return
        item_type = item.data(_TYPE_ROLE)
        if item_type not in ("setlist", "placeholder"):
            return
        prev_id = self._selected_id
        if item_type == "placeholder":
            self._select_placeholder()
        else:
            self._apply_setlist_item(item)
        self._allow_hide_popup = True
        self.hidePopup()
        if prev_id != self._selected_id:
            self.currentIndexChanged.emit(self.currentIndex())

    def _row_height(self) -> int:
        view = self.view()
        if view is None:
            return 24
        for row in range(self._model.rowCount()):
            h = view.sizeHintForRow(row)
            if h > 0:
                return h
        return view.fontMetrics().height() + 8

    def _count_total_rows(self) -> int:
        count = 0
        for row in range(self._model.rowCount()):
            top = self._model.item(row)
            if top is None:
                continue
            count += 1
            if top.data(_TYPE_ROLE) == "folder":
                count += top.rowCount()
        return count

    def _count_visible_rows(self) -> int:
        view = self.view()
        if view is None:
            return 0

        def walk(parent: QModelIndex) -> int:
            total = 0
            for row in range(self._model.rowCount(parent)):
                index = self._model.index(row, 0, parent)
                total += 1
                item = self._model.itemFromIndex(index)
                if item is not None and item.data(_TYPE_ROLE) == "folder" and view.isExpanded(index):
                    total += walk(index)
            return total

        return walk(QModelIndex())

    def _target_visible_rows(self) -> int:
        visible = self._count_visible_rows()
        total = self._count_total_rows()
        min_rows = min(_MIN_VISIBLE_ROWS, total) if total > 0 else _MIN_VISIBLE_ROWS
        return min(max(visible, min_rows), _MAX_VISIBLE_ROWS)

    def _update_popup_size(self) -> None:
        view = self.view()
        if view is None:
            return
        row_height = self._row_height()
        display_rows = self._target_visible_rows()
        height = display_rows * row_height + 6
        view.setFixedHeight(height)
        view.setMinimumWidth(max(self.width(), 280))
        popup = view.parentWidget()
        if popup is not None and popup is not view:
            popup.setFixedHeight(height)

    def _on_tree_structure_changed(self, _index: QModelIndex) -> None:
        if view := self.view():
            if view.isVisible():
                self._update_popup_size()

    def showPopup(self) -> None:
        super().showPopup()
        QTimer.singleShot(0, self._update_popup_size)
