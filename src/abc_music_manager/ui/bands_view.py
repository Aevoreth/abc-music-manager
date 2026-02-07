"""
Band management: bands, players, band members, band layouts and slots.
REQUIREMENTS §5.
"""

from __future__ import annotations

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
    QCheckBox,
    QMessageBox,
    QDialog,
    QFormLayout,
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
    add_player,
    update_player,
    delete_player,
    list_player_instruments,
    set_player_instrument,
    remove_player_instrument,
    PlayerRow,
)
from ..db.instrument import list_instruments


class BandsView(QWidget):
    def __init__(self, app_state: AppState, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.app_state = app_state
        self._selected_band_id: int | None = None
        self._selected_layout_id: int | None = None
        self._selected_player_id: int | None = None
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
        v.addWidget(QLabel("Players"))
        self.player_table = QTableWidget()
        self.player_table.setColumnCount(2)
        self.player_table.setHorizontalHeaderLabels(["Name", "Actions"])
        self.player_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.player_table.itemSelectionChanged.connect(self._on_player_selected)
        v.addWidget(self.player_table)
        add_pl_btn = QPushButton("Add player")
        add_pl_btn.clicked.connect(self._add_player)
        v.addWidget(add_pl_btn)

        self.player_detail = QGroupBox("Player detail — instruments & proficiency")
        pd_layout = QVBoxLayout(self.player_detail)
        self.player_instruments_table = QTableWidget()
        self.player_instruments_table.setColumnCount(4)
        self.player_instruments_table.setHorizontalHeaderLabels(["Instrument", "Has instrument", "Proficiency", "Remove"])
        pd_layout.addWidget(self.player_instruments_table)
        self.add_instrument_btn = QPushButton("Add instrument")
        self.add_instrument_btn.clicked.connect(self._add_player_instrument)
        pd_layout.addWidget(self.add_instrument_btn)
        v.addWidget(self.player_detail)
        self.player_detail.setEnabled(False)
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
        from PySide6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, "New player", "Player name:")
        if ok and name and name.strip():
            add_player(self.app_state.conn, name.strip())
            self._refresh_players()

    def _on_player_selected(self) -> None:
        row = self.player_table.currentRow()
        if row < 0:
            self._selected_player_id = None
            self.player_detail.setEnabled(False)
            return
        players = list_players(self.app_state.conn)
        if row >= len(players):
            return
        self._selected_player_id = players[row].id
        self.player_detail.setEnabled(True)
        self._refresh_player_instruments()

    def _refresh_players(self) -> None:
        players = list_players(self.app_state.conn)
        self.player_table.setRowCount(len(players))
        for i, p in enumerate(players):
            self.player_table.setItem(i, 0, QTableWidgetItem(p.name))
            btn = QPushButton("Delete")
            btn.clicked.connect(lambda checked=False, pl=p: self._delete_player(pl))
            self.player_table.setCellWidget(i, 1, btn)
        self.player_table.setRowCount(len(players))

    def _refresh_player_instruments(self) -> None:
        if self._selected_player_id is None:
            return
        rows = list_player_instruments(self.app_state.conn, self._selected_player_id)
        self.player_instruments_table.setRowCount(len(rows))
        for i, (iid, iname, has_inv, prof) in enumerate(rows):
            self.player_instruments_table.setItem(i, 0, QTableWidgetItem(iname))
            self.player_instruments_table.setItem(i, 1, QTableWidgetItem("Yes" if has_inv else "No"))
            prof_cb = QCheckBox()
            prof_cb.setChecked(prof)
            prof_cb.stateChanged.connect(lambda state, inst_id=iid: self._set_proficiency(inst_id, state == Qt.CheckState.Checked))
            self.player_instruments_table.setCellWidget(i, 2, prof_cb)
            btn = QPushButton("Remove")
            btn.clicked.connect(lambda checked=False, inst_id=iid: self._remove_player_instrument(inst_id))
            self.player_instruments_table.setCellWidget(i, 3, btn)
        self.player_instruments_table.setRowCount(len(rows))

    def _delete_player(self, player: PlayerRow) -> None:
        if QMessageBox.question(self, "Confirm", f"Delete player '{player.name}'?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            delete_player(self.app_state.conn, player.id)
            self._selected_player_id = None
            self._refresh_players()

    def _add_player_instrument(self) -> None:
        if self._selected_player_id is None:
            return
        instruments = list_instruments(self.app_state.conn)
        existing_ids = {r[0] for r in list_player_instruments(self.app_state.conn, self._selected_player_id)}
        available = [(iid, name) for iid, name in instruments if iid not in existing_ids]
        if not available:
            QMessageBox.information(self, "Info", "All instruments already added, or add instruments in Settings/parsing first.")
            return
        from PySide6.QtWidgets import QInputDialog
        names = [n for _, n in available]
        name, ok = QInputDialog.getItem(self, "Add instrument", "Instrument:", names, 0, False)
        if ok and name:
            iid = next(iid for iid, n in available if n == name)
            set_player_instrument(self.app_state.conn, self._selected_player_id, iid, has_instrument=True, has_proficiency=False)
            self._refresh_player_instruments()

    def _set_proficiency(self, instrument_id: int, has_proficiency: bool) -> None:
        if self._selected_player_id is None:
            return
        set_player_instrument(
            self.app_state.conn,
            self._selected_player_id,
            instrument_id,
            has_instrument=True,
            has_proficiency=has_proficiency,
        )

    def _remove_player_instrument(self, instrument_id: int) -> None:
        if self._selected_player_id is None:
            return
        remove_player_instrument(self.app_state.conn, self._selected_player_id, instrument_id)
        self._refresh_player_instruments()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._refresh_bands()
        self._refresh_players()
