"""
Setlist manager: create/edit setlists, add songs, assign song layouts, reorder.
REQUIREMENTS §6.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
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
    QGroupBox,
    QHeaderView,
)
from PySide6.QtCore import Qt

from ..services.app_state import AppState
from ..db import list_library_songs
from ..db.setlist_repo import (
    list_setlists,
    add_setlist,
    update_setlist,
    delete_setlist,
    list_setlist_items,
    add_setlist_item,
    update_setlist_item,
    remove_setlist_item,
    reorder_setlist_items,
    SetlistRow,
    SetlistItemRow,
)
from ..db.song_layout_repo import (
    list_song_layouts_for_song_and_band,
    add_song_layout,
    set_song_layout_assignment,
    get_song_layout_assignments,
    list_song_layouts_for_song,
)
from ..db.band_repo import list_all_band_layouts, list_band_layouts, list_band_members


class SetlistsView(QWidget):
    def __init__(self, app_state: AppState, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.app_state = app_state
        self._selected_setlist_id: int | None = None
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Setlists"))
        self.setlist_table = QTableWidget()
        self.setlist_table.setColumnCount(4)
        self.setlist_table.setHorizontalHeaderLabels(["Name", "Band layout", "Locked", "Actions"])
        self.setlist_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.setlist_table.itemSelectionChanged.connect(self._on_setlist_selected)
        layout.addWidget(self.setlist_table)
        h = QHBoxLayout()
        add_btn = QPushButton("Add setlist")
        add_btn.clicked.connect(self._add_setlist)
        h.addWidget(add_btn)
        layout.addLayout(h)

        self.detail_group = QGroupBox("Setlist detail")
        detail_layout = QVBoxLayout(self.detail_group)
        detail_layout.addWidget(QLabel("Name:"))
        self.setlist_name_edit = QLineEdit()
        detail_layout.addWidget(self.setlist_name_edit)
        detail_layout.addWidget(QLabel("Band layout (required for play):"))
        self.band_layout_combo = QComboBox()
        self.band_layout_combo.currentIndexChanged.connect(self._on_band_layout_changed)
        detail_layout.addWidget(self.band_layout_combo)
        detail_layout.addWidget(QLabel("Locked (no edit, excluded from Add to Set):"))
        self.locked_check = QCheckBox("Locked")
        detail_layout.addWidget(self.locked_check)
        detail_layout.addWidget(QLabel("Default change duration (seconds):"))
        self.default_duration_spin = QSpinBox()
        self.default_duration_spin.setRange(0, 300)
        self.default_duration_spin.setSpecialValueText("—")
        detail_layout.addWidget(self.default_duration_spin)
        save_btn = QPushButton("Save setlist")
        save_btn.clicked.connect(self._save_setlist)
        detail_layout.addWidget(save_btn)

        detail_layout.addWidget(QLabel("Items:"))
        self.items_table = QTableWidget()
        self.items_table.setColumnCount(5)
        self.items_table.setHorizontalHeaderLabels(["#", "Song", "Song layout", "Override (s)", "Actions"])
        self.items_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        detail_layout.addWidget(self.items_table)
        h2 = QHBoxLayout()
        add_item_btn = QPushButton("Add song")
        add_item_btn.clicked.connect(self._add_item)
        h2.addWidget(add_item_btn)
        detail_layout.addLayout(h2)
        layout.addWidget(self.detail_group)
        self.detail_group.setEnabled(False)

    def _refresh_setlists(self) -> None:
        rows = list_setlists(self.app_state.conn)
        self.setlist_table.setRowCount(len(rows))
        layouts = {r[0]: (r[1], r[2]) for r in list_all_band_layouts(self.app_state.conn)}
        for i, s in enumerate(rows):
            self.setlist_table.setItem(i, 0, QTableWidgetItem(s.name))
            bl_name = "—"
            if s.band_layout_id and s.band_layout_id in layouts:
                bl_name = layouts[s.band_layout_id][0]
            self.setlist_table.setItem(i, 1, QTableWidgetItem(bl_name))
            self.setlist_table.setItem(i, 2, QTableWidgetItem("Yes" if s.locked else "No"))
            del_btn = QPushButton("Delete")
            del_btn.clicked.connect(lambda checked=False, sl=s: self._delete_setlist(sl))
            self.setlist_table.setCellWidget(i, 3, del_btn)
        self.setlist_table.setRowCount(len(rows))

    def _on_setlist_selected(self) -> None:
        row = self.setlist_table.currentRow()
        if row < 0:
            self._selected_setlist_id = None
            self.detail_group.setEnabled(False)
            return
        rows = list_setlists(self.app_state.conn)
        if row >= len(rows):
            return
        self._selected_setlist_id = rows[row].id
        self.detail_group.setEnabled(True)
        s = rows[row]
        self.setlist_name_edit.setText(s.name)
        self.locked_check.setChecked(s.locked)
        self.default_duration_spin.setValue(s.default_change_duration_seconds or 0)
        self._load_band_layout_combo()
        for i in range(self.band_layout_combo.count()):
            if self.band_layout_combo.itemData(i) == s.band_layout_id:
                self.band_layout_combo.setCurrentIndex(i)
                break
        else:
            self.band_layout_combo.setCurrentIndex(0)
        self._refresh_items()

    def _load_band_layout_combo(self) -> None:
        self.band_layout_combo.clear()
        self.band_layout_combo.addItem("(draft — select for play)", None)
        for layout_id, layout_name, band_name in list_all_band_layouts(self.app_state.conn):
            self.band_layout_combo.addItem(f"{band_name} — {layout_name}", layout_id)
        self.band_layout_combo.setCurrentIndex(0)

    def _on_band_layout_changed(self) -> None:
        pass

    def _refresh_items(self) -> None:
        if self._selected_setlist_id is None:
            return
        items_with_titles = list_setlist_items(self.app_state.conn, self._selected_setlist_id)
        self.items_table.setRowCount(len(items_with_titles))
        for i, (item, song_title) in enumerate(items_with_titles):
            self.items_table.setItem(i, 0, QTableWidgetItem(str(item.position + 1)))
            self.items_table.setItem(i, 1, QTableWidgetItem(song_title))
            layout_name = "—"
            if item.song_layout_id:
                cur = self.app_state.conn.execute("SELECT name FROM SongLayout WHERE id = ?", (item.song_layout_id,))
                r = cur.fetchone()
                layout_name = r[0] if r and r[0] else f"Layout #{item.song_layout_id}"
            self.items_table.setItem(i, 2, QTableWidgetItem(layout_name))
            self.items_table.setItem(i, 3, QTableWidgetItem(str(item.override_change_duration_seconds) if item.override_change_duration_seconds is not None else "—"))
            w = QWidget()
            h = QHBoxLayout(w)
            up_btn = QPushButton("Up")
            up_btn.clicked.connect(lambda checked=False, idx=i: self._move_item(idx, -1))
            down_btn = QPushButton("Down")
            down_btn.clicked.connect(lambda checked=False, idx=i: self._move_item(idx, 1))
            choose_btn = QPushButton("Layout...")
            choose_btn.clicked.connect(lambda checked=False, it=item: self._choose_song_layout(it))
            rem_btn = QPushButton("Remove")
            rem_btn.clicked.connect(lambda checked=False, it=item: self._remove_item(it))
            h.addWidget(up_btn)
            h.addWidget(down_btn)
            h.addWidget(choose_btn)
            h.addWidget(rem_btn)
            self.items_table.setCellWidget(i, 4, w)
        self.items_table.setRowCount(len(items_with_titles))

    def _add_setlist(self) -> None:
        name, ok = QInputDialog.getText(self, "New setlist", "Setlist name:")
        if ok and name and name.strip():
            add_setlist(self.app_state.conn, name.strip())
            self._refresh_setlists()

    def _save_setlist(self) -> None:
        if self._selected_setlist_id is None:
            return
        name = self.setlist_name_edit.text().strip()
        if not name:
            return
        bl_id = self.band_layout_combo.currentData()
        update_setlist(
            self.app_state.conn,
            self._selected_setlist_id,
            name=name,
            band_layout_id=bl_id,
            locked=self.locked_check.isChecked(),
            default_change_duration_seconds=self.default_duration_spin.value() or None,
        )
        self._refresh_setlists()

    def _delete_setlist(self, s: SetlistRow) -> None:
        if QMessageBox.question(self, "Confirm", f"Delete setlist '{s.name}'?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            delete_setlist(self.app_state.conn, s.id)
            self._selected_setlist_id = None
            self._refresh_setlists()

    def _add_item(self) -> None:
        if self._selected_setlist_id is None:
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
        setlist = next(s for s in list_setlists(self.app_state.conn) if s.id == self._selected_setlist_id)
        band_layout_id = setlist.band_layout_id
        song_layout_id = None
        if band_layout_id:
            layouts = list_song_layouts_for_song_and_band(self.app_state.conn, song_id, band_layout_id)
            if layouts:
                names = [lay.name or f"Layout {lay.id}" for lay in layouts]
                name, ok2 = QInputDialog.getItem(self, "Song layout", "Use layout:", names, 0, False)
                if ok2 and name:
                    song_layout_id = next(lay.id for lay in layouts if (lay.name or f"Layout {lay.id}") == name)
            else:
                if QMessageBox.question(self, "Create layout", "No song layout for this band. Create one?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.Yes) == QMessageBox.StandardButton.Yes:
                    layout_name, ok3 = QInputDialog.getText(self, "New song layout", "Layout name:")
                    if ok3 and layout_name:
                        song_layout_id = add_song_layout(self.app_state.conn, song_id, band_layout_id, layout_name.strip())
                        row = self.app_state.conn.execute("SELECT band_id FROM BandLayout WHERE id = ?", (band_layout_id,)).fetchone()
                        if row:
                            band_id = row[0]
                            for player_id in list_band_members(self.app_state.conn, band_id):
                                set_song_layout_assignment(self.app_state.conn, song_layout_id, player_id, None)
        items = list_setlist_items(self.app_state.conn, self._selected_setlist_id)
        position = len(items)
        add_setlist_item(self.app_state.conn, self._selected_setlist_id, song_id, position, song_layout_id=song_layout_id)
        self._refresh_items()

    def _move_item(self, index: int, delta: int) -> None:
        if self._selected_setlist_id is None:
            return
        items_with_titles = list_setlist_items(self.app_state.conn, self._selected_setlist_id)
        if not items_with_titles or index + delta < 0 or index + delta >= len(items_with_titles):
            return
        ids = [it[0].id for it in items_with_titles]
        ids[index], ids[index + delta] = ids[index + delta], ids[index]
        reorder_setlist_items(self.app_state.conn, self._selected_setlist_id, ids)
        self._refresh_items()

    def _choose_song_layout(self, item: SetlistItemRow) -> None:
        setlist = next(s for s in list_setlists(self.app_state.conn) if s.id == item.setlist_id)
        if not setlist.band_layout_id:
            QMessageBox.information(self, "Info", "Set a band layout on the setlist first.")
            return
        layouts = list_song_layouts_for_song_and_band(self.app_state.conn, item.song_id, setlist.band_layout_id)
        if not layouts:
            QMessageBox.information(self, "Info", "No song layout for this song and band. Create one from Song detail or when adding.")
            return
        names = [lay.name or f"Layout {lay.id}" for lay in layouts]
        name, ok = QInputDialog.getItem(self, "Song layout", "Layout:", names, 0, False)
        if ok and name:
            layout_id = next(lay.id for lay in layouts if (lay.name or f"Layout {lay.id}") == name)
            update_setlist_item(self.app_state.conn, item.id, song_layout_id=layout_id)
            self._refresh_items()

    def _remove_item(self, item: SetlistItemRow) -> None:
        remove_setlist_item(self.app_state.conn, item.id)
        self._refresh_items()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._refresh_setlists()
