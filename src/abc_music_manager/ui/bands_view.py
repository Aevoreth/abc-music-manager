"""
Band management: bands, players, band members, band layouts and slots.
REQUIREMENTS §5.
"""

from __future__ import annotations

from math import sqrt

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QPushButton,
    QLabel,
    QLineEdit,
    QComboBox,
    QSpinBox,
    QMessageBox,
    QGroupBox,
    QHeaderView,
)
from PySide6.QtCore import Qt

from ..services.app_state import AppState
from ..db.band_repo import (
    list_bands,
    add_band,
    update_band,
    delete_band,
    list_band_members,
    add_band_member,
    remove_band_member,
    list_band_layouts,
    add_band_layout,
    update_band_layout,
    delete_band_layout,
    list_layout_slots,
    set_layout_slot,
    remove_layout_slot,
    BandRow,
    BandLayoutRow,
)
from ..db.player_repo import (
    list_players,
    delete_player,
    list_player_instruments_bulk,
    PlayerRow,
)
from ..db.instrument import get_or_create_instruments_by_names
from ..db.schema import PLAYER_INSTRUMENTS
from .player_dialog import open_new_character_dialog, open_edit_character_dialog
from .diagonal_header import DiagonalHeaderView


class BandsView(QWidget):
    def __init__(self, app_state: AppState, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.app_state = app_state
        self._selected_band_id: int | None = None
        self._selected_layout_id: int | None = None
        self._instrument_name_to_id: dict[str, int] = {}
        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_bands_tab(), "Bands")
        self.tabs.addTab(self._build_players_tab(), "Players")
        layout.addWidget(self.tabs)

    def _build_bands_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.addWidget(QLabel("Bands"))
        self.band_table = QTableWidget()
        self.band_table.setColumnCount(2)
        self.band_table.setHorizontalHeaderLabels(["Name", "Actions"])
        self.band_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.band_table.itemSelectionChanged.connect(self._on_band_selected)
        v.addWidget(self.band_table)
        h = QHBoxLayout()
        add_band_btn = QPushButton("Add band")
        add_band_btn.clicked.connect(self._add_band)
        h.addWidget(add_band_btn)
        v.addLayout(h)

        self.band_detail = QGroupBox("Band detail")
        band_detail_layout = QVBoxLayout(self.band_detail)
        self.band_name_edit = QLineEdit()
        self.band_name_edit.setPlaceholderText("Band name")
        band_detail_layout.addWidget(QLabel("Name:"))
        band_detail_layout.addWidget(self.band_name_edit)
        self.save_band_btn = QPushButton("Save band name")
        self.save_band_btn.clicked.connect(self._save_band_name)
        band_detail_layout.addWidget(self.save_band_btn)

        band_detail_layout.addWidget(QLabel("Members (players in this band):"))
        self.members_list = QTableWidget()
        self.members_list.setColumnCount(2)
        self.members_list.setHorizontalHeaderLabels(["Player", "Remove"])
        band_detail_layout.addWidget(self.members_list)
        self.add_member_btn = QPushButton("Add member")
        self.add_member_btn.clicked.connect(self._add_band_member)
        band_detail_layout.addWidget(self.add_member_btn)

        band_detail_layout.addWidget(QLabel("Layouts:"))
        self.layouts_list = QTableWidget()
        self.layouts_list.setColumnCount(3)
        self.layouts_list.setHorizontalHeaderLabels(["Name", "Edit slots", "Delete"])
        self.layouts_list.itemSelectionChanged.connect(self._on_layout_selected)
        band_detail_layout.addWidget(self.layouts_list)
        self.add_layout_btn = QPushButton("Add layout")
        self.add_layout_btn.clicked.connect(self._add_layout)
        band_detail_layout.addWidget(self.add_layout_btn)

        self.layout_slots_group = QGroupBox("Layout slots (position player cards)")
        self.layout_slots_layout = QVBoxLayout(self.layout_slots_group)
        self.slots_table = QTableWidget()
        self.slots_table.setColumnCount(4)
        self.slots_table.setHorizontalHeaderLabels(["Player", "X", "Y", "Remove"])
        self.layout_slots_layout.addWidget(self.slots_table)
        self.add_slot_btn = QPushButton("Add slot")
        self.add_slot_btn.clicked.connect(self._add_slot)
        self.layout_slots_layout.addWidget(self.add_slot_btn)
        band_detail_layout.addWidget(self.layout_slots_group)

        v.addWidget(self.band_detail)
        self.band_detail.setEnabled(False)
        return w

    def _build_players_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        # Filter row
        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Name:"))
        self.player_name_filter = QLineEdit()
        self.player_name_filter.setPlaceholderText("Filter by name")
        self.player_name_filter.setClearButtonEnabled(True)
        self.player_name_filter.setMaximumWidth(180)
        self.player_name_filter.textChanged.connect(self._apply_player_filters)
        filter_row.addWidget(self.player_name_filter)
        filter_row.addWidget(QLabel("Level:"))
        self.player_level_min = QSpinBox()
        self.player_level_min.setRange(0, 150)
        self.player_level_min.setSpecialValueText("—")
        self.player_level_min.setValue(0)
        self.player_level_min.valueChanged.connect(self._apply_player_filters)
        filter_row.addWidget(self.player_level_min)
        filter_row.addWidget(QLabel("to"))
        self.player_level_max = QSpinBox()
        self.player_level_max.setRange(0, 150)
        self.player_level_max.setSpecialValueText("—")
        self.player_level_max.setValue(0)
        self.player_level_max.valueChanged.connect(self._apply_player_filters)
        filter_row.addWidget(self.player_level_max)
        filter_row.addWidget(QLabel("Class:"))
        self.player_class_filter = QLineEdit()
        self.player_class_filter.setPlaceholderText("Filter by class")
        self.player_class_filter.setClearButtonEnabled(True)
        self.player_class_filter.setMaximumWidth(120)
        self.player_class_filter.textChanged.connect(self._apply_player_filters)
        filter_row.addWidget(self.player_class_filter)
        filter_row.addWidget(QLabel("Instrument:"))
        self.player_instrument_filter = QComboBox()
        self.player_instrument_filter.addItem("All", None)
        for name in PLAYER_INSTRUMENTS:
            self.player_instrument_filter.addItem(name, name)
        self.player_instrument_filter.currentIndexChanged.connect(self._apply_player_filters)
        filter_row.addWidget(self.player_instrument_filter)
        reset_btn = QPushButton("Reset Filters")
        reset_btn.clicked.connect(self._reset_player_filters)
        filter_row.addWidget(reset_btn)
        filter_row.addStretch()
        v.addLayout(filter_row)

        # New Character button (width = text width)
        self.new_character_btn = QPushButton("New Character")
        self.new_character_btn.clicked.connect(self._add_player)
        fm = self.new_character_btn.fontMetrics()
        self.new_character_btn.setFixedWidth(fm.horizontalAdvance("New Character") + 24)
        v.addWidget(self.new_character_btn)

        # Players table
        num_instruments = len(PLAYER_INSTRUMENTS)
        num_cols = 4 + num_instruments  # Name, Level, Class, instruments..., Actions
        self.player_table = QTableWidget()
        self.player_table.setColumnCount(num_cols)
        headers = ["Name", "Level", "Class"] + list(PLAYER_INSTRUMENTS) + ["Actions"]
        self.player_table.setHorizontalHeaderLabels(headers)
        header = DiagonalHeaderView(
            self.player_table,
            diagonal_start=3,
            diagonal_end=3 + num_instruments - 1,
        )
        self.player_table.setHorizontalHeader(header)
        # Ensure header has enough height for diagonal text (longest instrument name)
        fm = header.fontMetrics()
        max_diag = max(
            (fm.horizontalAdvance(name) + fm.height()) / sqrt(2)
            for name in PLAYER_INSTRUMENTS
        )
        header.setMinimumHeight(int(max_diag) + 12)
        for col in range(3, 3 + num_instruments):
            self.player_table.horizontalHeader().setSectionResizeMode(col, QHeaderView.ResizeMode.Fixed)
            self.player_table.horizontalHeader().resizeSection(col, 26)
        self.player_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        v.addWidget(self.player_table)
        return w

    def _refresh_bands(self) -> None:
        bands = list_bands(self.app_state.conn)
        self.band_table.setRowCount(len(bands))
        for i, b in enumerate(bands):
            self.band_table.setItem(i, 0, QTableWidgetItem(b.name))
            btn = QPushButton("Delete")
            btn.clicked.connect(lambda checked=False, band=b: self._delete_band(band))
            self.band_table.setCellWidget(i, 1, btn)
        self.band_table.setRowCount(len(bands))

    def _on_band_selected(self) -> None:
        row = self.band_table.currentRow()
        if row < 0:
            self._selected_band_id = None
            self.band_detail.setEnabled(False)
            return
        bands = list_bands(self.app_state.conn)
        if row >= len(bands):
            return
        self._selected_band_id = bands[row].id
        self.band_detail.setEnabled(True)
        self.band_name_edit.setText(bands[row].name)
        self._refresh_members()
        self._refresh_layouts()
        self._selected_layout_id = None
        self.layout_slots_group.setEnabled(False)

    def _refresh_members(self) -> None:
        if self._selected_band_id is None:
            return
        player_ids = list_band_members(self.app_state.conn, self._selected_band_id)
        players = {p.id: p.name for p in list_players(self.app_state.conn)}
        self.members_list.setRowCount(len(player_ids))
        for i, pid in enumerate(player_ids):
            self.members_list.setItem(i, 0, QTableWidgetItem(players.get(pid, str(pid))))
            btn = QPushButton("Remove")
            btn.clicked.connect(lambda checked=False, p=pid: self._remove_member(p))
            self.members_list.setCellWidget(i, 1, btn)
        self.members_list.setRowCount(len(player_ids))

    def _refresh_layouts(self) -> None:
        if self._selected_band_id is None:
            return
        layouts = list_band_layouts(self.app_state.conn, self._selected_band_id)
        self.layouts_list.setRowCount(len(layouts))
        for i, lay in enumerate(layouts):
            self.layouts_list.setItem(i, 0, QTableWidgetItem(lay.name))
            edit_btn = QPushButton("Edit slots")
            edit_btn.clicked.connect(lambda checked=False, l=lay: self._edit_layout_slots(l))
            self.layouts_list.setCellWidget(i, 1, edit_btn)
            del_btn = QPushButton("Delete")
            del_btn.clicked.connect(lambda checked=False, l=lay: self._delete_layout(l))
            self.layouts_list.setCellWidget(i, 2, del_btn)
        self.layouts_list.setRowCount(len(layouts))

    def _on_layout_selected(self) -> None:
        row = self.layouts_list.currentRow()
        if row < 0 or self._selected_band_id is None:
            self._selected_layout_id = None
            self.layout_slots_group.setEnabled(False)
            return
        layouts = list_band_layouts(self.app_state.conn, self._selected_band_id)
        if row >= len(layouts):
            return
        self._selected_layout_id = layouts[row].id
        self.layout_slots_group.setEnabled(True)
        self._refresh_slots()

    def _refresh_slots(self) -> None:
        if self._selected_layout_id is None:
            return
        slots = list_layout_slots(self.app_state.conn, self._selected_layout_id)
        players = {p.id: p.name for p in list_players(self.app_state.conn)}
        self.slots_table.setRowCount(len(slots))
        for i, s in enumerate(slots):
            self.slots_table.setItem(i, 0, QTableWidgetItem(players.get(s.player_id, str(s.player_id))))
            self.slots_table.setItem(i, 1, QTableWidgetItem(str(s.x)))
            self.slots_table.setItem(i, 2, QTableWidgetItem(str(s.y)))
            btn = QPushButton("Remove")
            btn.clicked.connect(lambda checked=False, slot=s: self._remove_slot(slot))
            self.slots_table.setCellWidget(i, 3, btn)
        self.slots_table.setRowCount(len(slots))

    def _add_band(self) -> None:
        from PySide6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, "New band", "Band name:")
        if ok and name and name.strip():
            add_band(self.app_state.conn, name.strip())
            self._refresh_bands()

    def _save_band_name(self) -> None:
        if self._selected_band_id is None:
            return
        name = self.band_name_edit.text().strip()
        if name:
            update_band(self.app_state.conn, self._selected_band_id, name)
            self._refresh_bands()

    def _delete_band(self, band: BandRow) -> None:
        if QMessageBox.question(self, "Confirm", f"Delete band '{band.name}'?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            delete_band(self.app_state.conn, band.id)
            self._selected_band_id = None
            self._refresh_bands()

    def _add_band_member(self) -> None:
        if self._selected_band_id is None:
            return
        players = list_players(self.app_state.conn)
        existing = set(list_band_members(self.app_state.conn, self._selected_band_id))
        available = [p for p in players if p.id not in existing]
        if not available:
            QMessageBox.information(self, "Info", "All players are already in this band.")
            return
        from PySide6.QtWidgets import QInputDialog
        names = [p.name for p in available]
        name, ok = QInputDialog.getItem(self, "Add member", "Player:", names, 0, False)
        if ok and name:
            pid = next(p.id for p in available if p.name == name)
            add_band_member(self.app_state.conn, self._selected_band_id, pid)
            self._refresh_members()

    def _remove_member(self, player_id: int) -> None:
        if self._selected_band_id is None:
            return
        remove_band_member(self.app_state.conn, self._selected_band_id, player_id)
        self._refresh_members()

    def _add_layout(self) -> None:
        if self._selected_band_id is None:
            return
        from PySide6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, "New layout", "Layout name:")
        if ok and name and name.strip():
            add_band_layout(self.app_state.conn, self._selected_band_id, name.strip())
            self._refresh_layouts()

    def _edit_layout_slots(self, layout: BandLayoutRow) -> None:
        self._selected_layout_id = layout.id
        self.layout_slots_group.setEnabled(True)
        self._refresh_slots()
        for i in range(self.layouts_list.rowCount()):
            if self.layouts_list.item(i, 0).text() == layout.name:
                self.layouts_list.selectRow(i)
                break

    def _delete_layout(self, layout: BandLayoutRow) -> None:
        if QMessageBox.question(self, "Confirm", f"Delete layout '{layout.name}'?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            delete_band_layout(self.app_state.conn, layout.id)
            self._selected_layout_id = None
            self._refresh_layouts()

    def _add_slot(self) -> None:
        if self._selected_layout_id is None:
            return
        players = list_players(self.app_state.conn)
        band_id = next((b.id for b in list_bands(self.app_state.conn) for lay in list_band_layouts(self.app_state.conn, b.id) if lay.id == self._selected_layout_id), None)
        if band_id is None:
            return
        member_ids = set(list_band_members(self.app_state.conn, band_id))
        existing_slots = list_layout_slots(self.app_state.conn, self._selected_layout_id)
        existing_player_ids = {s.player_id for s in existing_slots}
        available = [p for p in players if p.id in member_ids and p.id not in existing_player_ids]
        if not available:
            QMessageBox.information(self, "Info", "No more players to add, or add members to the band first.")
            return
        from PySide6.QtWidgets import QInputDialog
        names = [p.name for p in available]
        name, ok = QInputDialog.getItem(self, "Add slot", "Player:", names, 0, False)
        if ok and name:
            pid = next(p.id for p in available if p.name == name)
            x, okx = QInputDialog.getInt(self, "Position", "X:", 0, 0, 100)
            y, oky = QInputDialog.getInt(self, "Position", "Y:", 0, 0, 100)
            if okx and oky:
                set_layout_slot(self.app_state.conn, self._selected_layout_id, pid, x, y)
                self._refresh_slots()

    def _remove_slot(self, slot) -> None:
        remove_layout_slot(self.app_state.conn, slot.band_layout_id, slot.player_id)
        self._refresh_slots()

    def _add_player(self) -> None:
        if open_new_character_dialog(self.app_state, self):
            self._refresh_players()

    def _reset_player_filters(self) -> None:
        self.player_name_filter.clear()
        self.player_level_min.setValue(0)
        self.player_level_max.setValue(0)
        self.player_class_filter.clear()
        self.player_instrument_filter.setCurrentIndex(0)
        self._refresh_players()

    def _apply_player_filters(self) -> None:
        self._refresh_players()

    def _refresh_players(self) -> None:
        name_sub = self.player_name_filter.text().strip() or None
        level_min = self.player_level_min.value() if self.player_level_min.value() > 0 else None
        level_max = self.player_level_max.value() if self.player_level_max.value() > 0 else None
        class_sub = self.player_class_filter.text().strip() or None
        instrument_ids = None
        inst_name = self.player_instrument_filter.currentData()
        if inst_name:
            if not self._instrument_name_to_id:
                self._instrument_name_to_id = get_or_create_instruments_by_names(
                    self.app_state.conn, PLAYER_INSTRUMENTS
                )
            if inst_name in self._instrument_name_to_id:
                instrument_ids = [self._instrument_name_to_id[inst_name]]

        players = list_players(
            self.app_state.conn,
            name_substring=name_sub,
            level_min=level_min,
            level_max=level_max,
            class_substring=class_sub,
            instrument_ids=instrument_ids,
        )
        if not self._instrument_name_to_id:
            self._instrument_name_to_id = get_or_create_instruments_by_names(
                self.app_state.conn, PLAYER_INSTRUMENTS
            )
        instrument_ids_list = [self._instrument_name_to_id[n] for n in PLAYER_INSTRUMENTS]
        bulk = list_player_instruments_bulk(self.app_state.conn, [p.id for p in players])

        num_instruments = len(PLAYER_INSTRUMENTS)
        self.player_table.setRowCount(len(players))
        for i, p in enumerate(players):
            self.player_table.setItem(i, 0, QTableWidgetItem(p.name))
            self.player_table.setItem(i, 1, QTableWidgetItem(str(p.level) if p.level is not None else ""))
            self.player_table.setItem(i, 2, QTableWidgetItem(p.class_ or ""))
            has_set = bulk.get(p.id, set())
            for j, iid in enumerate(instrument_ids_list):
                item = QTableWidgetItem("\u2713" if iid in has_set else "")
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.player_table.setItem(i, 3 + j, item)
            actions_widget = QWidget()
            actions_layout = QHBoxLayout(actions_widget)
            actions_layout.setContentsMargins(2, 0, 2, 0)
            edit_btn = QPushButton("Edit")
            edit_btn.clicked.connect(lambda checked=False, pl=p: self._edit_player(pl))
            del_btn = QPushButton("Delete")
            del_btn.clicked.connect(lambda checked=False, pl=p: self._delete_player(pl))
            actions_layout.addWidget(edit_btn)
            actions_layout.addWidget(del_btn)
            self.player_table.setCellWidget(i, 3 + num_instruments, actions_widget)
        self.player_table.resizeRowsToContents()

    def _edit_player(self, player: PlayerRow) -> None:
        if open_edit_character_dialog(self.app_state, player, self):
            self._refresh_players()

    def _delete_player(self, player: PlayerRow) -> None:
        if QMessageBox.question(
            self,
            "Confirm",
            f"Delete player '{player.name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) == QMessageBox.StandardButton.Yes:
            delete_player(self.app_state.conn, player.id)
            self._refresh_players()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._refresh_bands()
        self._refresh_players()
