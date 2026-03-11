"""
New Character and Edit Character dialogs for the Players tab.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QLineEdit,
    QSpinBox,
    QComboBox,
    QPushButton,
    QDialogButtonBox,
    QGroupBox,
    QCheckBox,
    QScrollArea,
    QWidget,
)
from PySide6.QtCore import Qt

from ..services.app_state import AppState
from ..db.player_repo import add_player, update_player, list_player_instruments, set_player_instrument, PlayerRow
from ..db.schema import PLAYER_INSTRUMENTS
from ..db.instrument import get_or_create_instruments_by_names

# Instrument groups for the add/edit dialog
INSTRUMENT_GROUPS: dict[str, list[str]] = {
    "Fiddles": [
        "Basic Fiddle",
        "Student Fiddle",
        "Bardic Fiddle",
        "Lonely Mountain Fiddle",
        "Sprightly Fiddle",
        "Traveler's Trusty Fiddle",
    ],
    "Bassoons": [
        "Basic Bassoon",
        "Lonely Mountain Bassoon",
        "Brusque Bassoon",
    ],
    "Harps": [
        "Basic Harp",
        "Misty Mountain Harp",
    ],
    "Lutes": [
        "Basic Lute",
        "Lute of Ages",
    ],
    "Other": [
        "Basic Flute",
        "Basic Horn",
        "Basic Clarinet",
        "Basic Bagpipe",
        "Basic Pibgorn",
        "Basic Theorbo",
        "Basic Drum",
        "Basic Cowbell",
        "Moor Cowbell",
        "Jaunty Hand-Knells",
    ],
}

# Default unchecked for new characters
DEFAULT_UNCHECKED_INSTRUMENTS = {"Moor Cowbell", "Jaunty Hand-Knells"}

# Common LOTRO character classes; combo is editable for "Other"
LOTRO_CLASSES = [
    "Minstrel",
    "Hunter",
    "Burglar",
    "Captain",
    "Champion",
    "Guardian",
    "Lore-master",
    "Rune-keeper",
    "Warden",
    "Beorning",
    "Brawler",
    "Mariner",
]


def _save_player_instruments(conn, player_id: int, selected_names: set[str]) -> None:
    """Sync player instruments to match the selected set."""
    name_to_id = get_or_create_instruments_by_names(conn, PLAYER_INSTRUMENTS)
    for name in PLAYER_INSTRUMENTS:
        iid = name_to_id.get(name)
        if iid is not None:
            set_player_instrument(
                conn, player_id, iid,
                has_instrument=(name in selected_names),
                has_proficiency=False,
            )


def open_new_character_dialog(app_state: AppState, parent=None) -> bool:
    """Open New Character dialog. Returns True if a character was added."""
    dlg = PlayerDialog(app_state, parent=parent)
    if dlg.exec() == QDialog.DialogCode.Accepted:
        name = dlg.name_edit.text().strip()
        if name:
            level = dlg.level_spin.value() if dlg.level_spin.value() > 0 else None
            class_val = dlg.class_combo.currentText().strip() or None
            player_id = add_player(app_state.conn, name, level=level, class_=class_val)
            _save_player_instruments(app_state.conn, player_id, dlg.get_selected_instruments())
            return True
    return False


def open_edit_character_dialog(app_state: AppState, player: PlayerRow, parent=None) -> bool:
    """Open Edit Character dialog. Returns True if the character was updated."""
    dlg = PlayerDialog(app_state, player=player, parent=parent)
    if dlg.exec() == QDialog.DialogCode.Accepted:
        name = dlg.name_edit.text().strip()
        if name:
            level = dlg.level_spin.value() if dlg.level_spin.value() > 0 else None
            class_val = dlg.class_combo.currentText().strip() or None
            update_player(app_state.conn, player.id, name=name, level=level, class_=class_val)
            _save_player_instruments(app_state.conn, player.id, dlg.get_selected_instruments())
            return True
    return False


class PlayerDialog(QDialog):
    """Dialog for creating or editing a character (name, level, class, instruments)."""

    def __init__(
        self,
        app_state: AppState,
        player: PlayerRow | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.app_state = app_state
        self.player = player
        self._instrument_checkboxes: dict[str, QCheckBox] = {}
        self.setWindowTitle("Edit Character" if player else "New Character")
        self.setMinimumSize(400, 500)
        layout = QVBoxLayout(self)

        form = QFormLayout()
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Character name")
        self.name_edit.setMaxLength(200)
        form.addRow("Name:", self.name_edit)

        self.level_spin = QSpinBox()
        self.level_spin.setRange(0, 150)
        self.level_spin.setSpecialValueText("")
        self.level_spin.setValue(0)
        self.level_spin.setToolTip("0 or empty = not set")
        form.addRow("Level (optional):", self.level_spin)

        self.class_combo = QComboBox()
        self.class_combo.setEditable(True)
        self.class_combo.addItem("")
        for c in LOTRO_CLASSES:
            self.class_combo.addItem(c)
        self.class_combo.setCurrentIndex(0)
        form.addRow("Class (optional):", self.class_combo)

        layout.addLayout(form)

        # Instruments section (grouped)
        instruments_label = QGroupBox("Instruments")
        instruments_inner = QWidget()
        instruments_layout = QVBoxLayout(instruments_inner)
        for group_name, names in INSTRUMENT_GROUPS.items():
            group_box = QGroupBox(group_name)
            group_layout = QHBoxLayout(group_box)
            for name in names:
                cb = QCheckBox(name)
                default_checked = name not in DEFAULT_UNCHECKED_INSTRUMENTS
                cb.setChecked(default_checked)
                self._instrument_checkboxes[name] = cb
                group_layout.addWidget(cb)
            group_layout.addStretch()
            instruments_layout.addWidget(group_box)
        scroll = QScrollArea()
        scroll.setWidget(instruments_inner)
        scroll.setWidgetResizable(True)
        scroll.setMaximumHeight(220)
        instruments_main = QVBoxLayout(instruments_label)
        instruments_main.addWidget(scroll)
        layout.addWidget(instruments_label)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        if player:
            self.name_edit.setText(player.name)
            if player.level is not None:
                self.level_spin.setValue(player.level)
            if player.class_:
                idx = self.class_combo.findText(player.class_)
                if idx >= 0:
                    self.class_combo.setCurrentIndex(idx)
                else:
                    self.class_combo.setCurrentText(player.class_)
            # Load current instruments
            rows = list_player_instruments(app_state.conn, player.id)
            has_set = {name for _iid, name, has_inv, _prof in rows if has_inv}
            for name, cb in self._instrument_checkboxes.items():
                cb.setChecked(name in has_set)

    def get_selected_instruments(self) -> set[str]:
        """Return the set of instrument names that are checked."""
        return {name for name, cb in self._instrument_checkboxes.items() if cb.isChecked()}

    def _on_accept(self) -> None:
        if not self.name_edit.text().strip():
            return
        self.accept()
