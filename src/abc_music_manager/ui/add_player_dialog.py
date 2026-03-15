"""
Add Player dialog: searchable dropdown to pick a player for the band layout.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QComboBox,
    QPushButton,
    QDialogButtonBox,
)
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCompleter

from ..services.app_state import AppState
from ..db.player_repo import list_players


def open_add_player_dialog(
    app_state: AppState,
    exclude_player_ids: set[int],
    parent=None,
) -> tuple[int, str] | None:
    """
    Open Add Player dialog. Returns (player_id, player_name) if confirmed, else None.
    exclude_player_ids: players already in the layout to filter out.
    """
    dlg = AddPlayerDialog(app_state, exclude_player_ids, parent=parent)
    if dlg.exec() == QDialog.DialogCode.Accepted:
        return dlg.get_selected()
    return None


class AddPlayerDialog(QDialog):
    """Dialog with searchable combobox to select a player."""

    def __init__(
        self,
        app_state: AppState,
        exclude_player_ids: set[int],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.app_state = app_state
        self._exclude = exclude_player_ids
        self._players: list[tuple[int, str]] = []
        self.setWindowTitle("Add Player")
        self.setMinimumWidth(320)

        layout = QVBoxLayout(self)

        self._combo = QComboBox()
        self._combo.setEditable(True)
        self._combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self._combo.setMinimumWidth(280)
        completer = QCompleter(self._combo.model())
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self._combo.setCompleter(completer)
        layout.addWidget(self._combo)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._load_players()

    def _load_players(self) -> None:
        players = list_players(self.app_state.conn)
        self._players = [(p.id, p.name) for p in players if p.id not in self._exclude]
        self._combo.clear()
        for pid, name in self._players:
            self._combo.addItem(name, pid)
        if self._players:
            self._combo.setCurrentIndex(0)

    def _on_accept(self) -> None:
        pid = self._combo.currentData()
        if pid is not None:
            self.accept()

    def get_selected(self) -> tuple[int, str] | None:
        """Return (player_id, player_name) if a player was selected."""
        pid = self._combo.currentData()
        if pid is not None:
            return (pid, self._combo.currentText())
        return None
