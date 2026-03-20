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
    QSplitter,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
)
from PySide6.QtCore import Qt, QTimer

from ..services.app_state import AppState
from ..services.preferences import get_bands_splitter_state, set_bands_splitter_state
from ..db.band_repo import (
    list_bands,
    add_band,
    update_band,
    delete_band,
    list_band_members,
    add_band_member,
    list_band_layouts,
    add_band_layout,
    list_layout_slots,
    set_layout_slot,
    remove_layout_slot,
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
from .band_layout_grid import BandLayoutGridWidget, LayoutCard, SPAWN_X, SPAWN_Y, MAX_CARDS
from .add_player_dialog import open_add_player_dialog


class BandsView(QWidget):
    def __init__(self, app_state: AppState, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.app_state = app_state
        self._selected_band_id: int | None = None
        self._selected_layout_id: int | None = None
        self._instrument_name_to_id: dict[str, int] = {}
        self._loaded_band_name: str = ""
        self._loaded_band_notes: str = ""
        self._bands_splitter_restored: bool = False
        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_bands_tab(), "Bands")
        self.tabs.addTab(self._build_players_tab(), "Players")
        layout.addWidget(self.tabs)

    def _build_bands_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)

        # Top row: Add Band button
        add_band_btn = QPushButton("Add Band")
        fm = add_band_btn.fontMetrics()
        add_band_btn.setFixedWidth(fm.horizontalAdvance("Add Band") + 24)
        add_band_btn.clicked.connect(self._add_band)
        v.addWidget(add_band_btn)

        # Splitter: left = band list, right = band editor
        self.bands_splitter = QSplitter(Qt.Orientation.Horizontal)

        self.band_list = QListWidget()
        self.band_list.setWordWrap(True)
        self.band_list.setMinimumWidth(120)
        self.band_list.setMaximumWidth(300)
        self.band_list.currentRowChanged.connect(self._on_band_selected)
        self.bands_splitter.addWidget(self.band_list)

        self.band_editor = QWidget()
        editor_layout = QVBoxLayout(self.band_editor)

        # Top row: left = Save/Delete/Name, right = Notes
        top_row = QHBoxLayout()
        left_col = QVBoxLayout()
        btn_row = QHBoxLayout()
        self.save_band_btn = QPushButton("Save")
        self.save_band_btn.setFixedWidth(self.save_band_btn.fontMetrics().horizontalAdvance("Save") + 24)
        self.save_band_btn.clicked.connect(self._save_band)
        self.delete_band_btn = QPushButton("Delete")
        self.delete_band_btn.setFixedWidth(self.delete_band_btn.fontMetrics().horizontalAdvance("Delete") + 24)
        self.delete_band_btn.clicked.connect(self._delete_selected_band)
        btn_row.addWidget(self.save_band_btn)
        btn_row.addWidget(self.delete_band_btn)
        btn_row.addStretch()
        left_col.addLayout(btn_row)
        left_col.addWidget(QLabel("Band Name:"))
        self.band_name_edit = QLineEdit()
        self.band_name_edit.setPlaceholderText("Band name")
        left_col.addWidget(self.band_name_edit)

        right_col = QVBoxLayout()
        right_col.addWidget(QLabel("Notes:"))
        self.band_notes_edit = QPlainTextEdit()
        self.band_notes_edit.setPlaceholderText("Notes")
        self.band_notes_edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.band_notes_edit.setFixedHeight(75)
        right_col.addWidget(self.band_notes_edit)

        top_row.addLayout(left_col)
        top_row.addLayout(right_col)
        editor_layout.addLayout(top_row)

        # Grid
        self.layout_grid = BandLayoutGridWidget()
        self.layout_grid.setMinimumSize(300, 200)
        editor_layout.addWidget(self.layout_grid, 1)
        self.layout_grid.get_add_player_button().clicked.connect(self._add_player_to_layout)
        self.layout_grid.cardMoved.connect(self._on_card_moved)
        self.layout_grid.cardDeleted.connect(self._on_card_deleted)
        self.layout_grid.cardEditRequested.connect(self._on_card_edit_requested)

        self.bands_splitter.addWidget(self.band_editor)
        self.bands_splitter.setStretchFactor(1, 1)
        self._bands_splitter_save_timer = QTimer(self)
        self._bands_splitter_save_timer.setSingleShot(True)
        self._bands_splitter_save_timer.timeout.connect(
            lambda: set_bands_splitter_state(self.bands_splitter.sizes())
        )
        self.bands_splitter.splitterMoved.connect(
            lambda: self._bands_splitter_save_timer.start(150)
        )
        v.addWidget(self.bands_splitter)

        self.band_editor.setEnabled(False)
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

    def _refresh_band_list(self) -> None:
        bands = list_bands(self.app_state.conn)
        cur_id = self._selected_band_id
        self.band_list.blockSignals(True)
        self.band_list.clear()
        for b in bands:
            it = QListWidgetItem(b.name)
            it.setData(Qt.ItemDataRole.UserRole, b.id)
            self.band_list.addItem(it)
        need_load = False
        if cur_id is not None and bands:
            for i in range(self.band_list.count()):
                if self.band_list.item(i).data(Qt.ItemDataRole.UserRole) == cur_id:
                    self.band_list.setCurrentRow(i)
                    break
            else:
                need_load = True
        else:
            need_load = True
        if need_load and bands:
            self.band_list.setCurrentRow(0)
        self.band_list.blockSignals(False)
        if need_load:
            self._on_band_selected(0 if bands else -1)

    def _on_band_selected(self, row: int) -> None:
        if row < 0:
            self._selected_band_id = None
            self._selected_layout_id = None
            self._loaded_band_name = ""
            self._loaded_band_notes = ""
            self.band_editor.setEnabled(False)
            return
        item = self.band_list.item(row)
        if not item:
            return
        band_id = item.data(Qt.ItemDataRole.UserRole)
        bands = list_bands(self.app_state.conn)
        band = next((b for b in bands if b.id == band_id), None)
        if not band:
            return
        self._selected_band_id = band.id
        self._loaded_band_name = band.name
        self._loaded_band_notes = band.notes or ""
        self.band_editor.setEnabled(True)
        self.band_name_edit.setText(band.name)
        self.band_notes_edit.setPlainText(band.notes or "")

        layouts = list_band_layouts(self.app_state.conn, band.id)
        if layouts:
            self._selected_layout_id = layouts[0].id
        else:
            self._selected_layout_id = add_band_layout(self.app_state.conn, band.id, "Default")

        self._load_grid_from_layout()

    def _load_grid_from_layout(self) -> None:
        if self._selected_layout_id is None:
            self.layout_grid.set_cards([])
            return
        slots = list_layout_slots(self.app_state.conn, self._selected_layout_id)
        players = {p.id: p.name for p in list_players(self.app_state.conn)}
        cards = [
            LayoutCard(
                player_id=s.player_id,
                player_name=players.get(s.player_id, str(s.player_id)),
                x=s.x,
                y=s.y,
            )
            for s in slots
        ]
        self.layout_grid.set_cards(cards)

    def _add_band(self) -> None:
        bands = list_bands(self.app_state.conn)
        existing = sum(1 for b in bands if b.name.startswith("New Band"))
        name = f"New Band {existing + 1}"
        add_band(self.app_state.conn, name)
        self._refresh_band_list()
        for i, b in enumerate(list_bands(self.app_state.conn)):
            if b.name == name:
                self.band_list.setCurrentRow(i)
                break

    def _save_band(self) -> None:
        if self._selected_band_id is None or self._selected_layout_id is None:
            return
        name = self.band_name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Save", "Band name cannot be empty.")
            return
        notes = self.band_notes_edit.toPlainText().strip() or None

        has_overlap = self.layout_grid.has_any_overlap()
        if has_overlap:
            QMessageBox.warning(
                self,
                "Layout overlap",
                "Some cards overlap. Save is allowed, but consider rearranging.",
                QMessageBox.StandardButton.Ok,
            )

        update_band(self.app_state.conn, self._selected_band_id, name, notes=notes)

        cards = self.layout_grid.get_cards()
        existing_slots = list_layout_slots(self.app_state.conn, self._selected_layout_id)
        existing_player_ids = {s.player_id for s in existing_slots}
        for c in cards:
            add_band_member(self.app_state.conn, self._selected_band_id, c.player_id)
            set_layout_slot(self.app_state.conn, self._selected_layout_id, c.player_id, c.x, c.y)
        for s in existing_slots:
            if s.player_id not in {c.player_id for c in cards}:
                remove_layout_slot(self.app_state.conn, self._selected_layout_id, s.player_id)

        self._loaded_band_name = self.band_name_edit.text().strip()
        self._loaded_band_notes = self.band_notes_edit.toPlainText().strip() or ""
        self._refresh_band_list()
        self._load_grid_from_layout()

    def has_unsaved_changes(self) -> bool:
        """Return True if the Bands tab has unsaved edits (name or notes)."""
        if not self.band_editor.isEnabled() or self._selected_band_id is None:
            return False
        name = self.band_name_edit.text().strip()
        notes = self.band_notes_edit.toPlainText().strip() or ""
        return name != self._loaded_band_name or notes != self._loaded_band_notes

    def _delete_selected_band(self) -> None:
        if self._selected_band_id is None:
            return
        bands = list_bands(self.app_state.conn)
        band = next((b for b in bands if b.id == self._selected_band_id), None)
        if band and QMessageBox.question(
            self, "Confirm", f"Delete band '{band.name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) == QMessageBox.StandardButton.Yes:
            delete_band(self.app_state.conn, band.id)
            self._selected_band_id = None
            self._selected_layout_id = None
            self._loaded_band_name = ""
            self._loaded_band_notes = ""
            self._refresh_band_list()
            self.band_editor.setEnabled(False)

    def _add_player_to_layout(self) -> None:
        if self._selected_band_id is None or self._selected_layout_id is None:
            return
        cards = self.layout_grid.get_cards()
        if len(cards) >= MAX_CARDS:
            QMessageBox.information(self, "Add Player", f"Maximum {MAX_CARDS} cards allowed.")
            return
        exclude = {c.player_id for c in cards}
        result = open_add_player_dialog(self.app_state, exclude, self)
        if result:
            pid, pname = result
            add_band_member(self.app_state.conn, self._selected_band_id, pid)
            set_layout_slot(self.app_state.conn, self._selected_layout_id, pid, SPAWN_X, SPAWN_Y)
            card = LayoutCard(player_id=pid, player_name=pname, x=SPAWN_X, y=SPAWN_Y)
            self.layout_grid.add_card(card)

    def _on_card_moved(self, player_id: int, new_x: int, new_y: int) -> None:
        if self._selected_layout_id is None:
            return
        set_layout_slot(self.app_state.conn, self._selected_layout_id, player_id, new_x, new_y)

    def _on_card_deleted(self, player_id: int) -> None:
        if self._selected_layout_id is None:
            return
        remove_layout_slot(self.app_state.conn, self._selected_layout_id, player_id)
        self.layout_grid.remove_card(player_id)

    def _on_card_edit_requested(self, player_id: int) -> None:
        players = list_players(self.app_state.conn)
        player = next((p for p in players if p.id == player_id), None)
        if player and open_edit_character_dialog(self.app_state, player, self):
            self._load_grid_from_layout()

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
            _btn_style = "padding: 1px 4px; font-size: 11px; min-width: 22px;"
            edit_btn = QPushButton("Edit")
            edit_btn.setStyleSheet(_btn_style)
            edit_btn.clicked.connect(lambda checked=False, pl=p: self._edit_player(pl))
            del_btn = QPushButton("Delete")
            del_btn.setStyleSheet(_btn_style)
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
        # Defer refresh to next event loop so layout is ready
        QTimer.singleShot(0, self._on_show_deferred)
        # Defer splitter restore further so layout has settled (avoids reset-to-right)
        QTimer.singleShot(100, self._restore_bands_splitter)

    def _on_show_deferred(self) -> None:
        """Called after showEvent to ensure layout is ready before loading."""
        self._refresh_band_list()
        self._refresh_players()

    def _restore_bands_splitter(self) -> None:
        """Restore bands splitter from preferences. Runs after 100ms delay so layout is ready."""
        if self._bands_splitter_restored:
            return
        self._bands_splitter_restored = True
        total_now = self.bands_splitter.width()
        if total_now < 200:
            return  # Splitter not ready yet
        saved = get_bands_splitter_state()
        if saved and len(saved) >= 2:
            left_saved, right_saved = saved[0], saved[1]
            total_saved = left_saved + right_saved
            if total_saved > 0 and left_saved >= 120:
                # Scale proportionally when window size differs
                ratio = left_saved / total_saved
                left_now = int(total_now * ratio)
                left_now = max(120, min(300, left_now))  # Clamp to band_list min/max
                right_now = total_now - left_now
                self.bands_splitter.setSizes([left_now, right_now])
                return
        # Fallback: invalid or no saved state — use sensible default
        left_default = min(200, total_now - 120)
        left_default = max(120, min(300, left_default))
        self.bands_splitter.setSizes([left_default, total_now - left_default])
