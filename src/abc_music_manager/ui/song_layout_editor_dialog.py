"""
Dialog to create or edit a song layout: band selection and part-to-player assignment.
Only one layout per band per song. Setlists copy this data but are independent.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QComboBox,
    QPushButton,
    QWidget,
)
from PySide6.QtCore import Signal, Qt

from ..services.app_state import AppState
from ..db.band_repo import list_all_band_layouts
from ..db.song_layout_repo import (
    list_song_layouts_for_song,
    get_or_create_song_layout_for_band,
)
from .song_layout_assignment_panel import SongLayoutAssignmentPanel


class SongLayoutEditorDialog(QDialog):
    """Create or edit a song layout for a band."""

    song_layout_updated = Signal(int)  # song_layout_id

    def __init__(
        self,
        app_state: AppState,
        song_id: int,
        parts_json: str,
        song_layout_id: int | None = None,
        band_layout_id: int | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.app_state = app_state
        self.song_id = song_id
        self.parts_json = parts_json or "[]"
        self._song_layout_id = song_layout_id
        self._band_layout_id = band_layout_id
        self.setWindowTitle("Edit song layout" if song_layout_id else "New song layout")
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowModality(Qt.WindowModality.NonModal)
        # Size to fit 6 cards wide × 3 cards deep (CARD 9×7 units @ 15px/unit + padding)
        self.setMinimumSize(950, 520)
        self.resize(950, 520)

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Band layout:"))
        self.band_layout_combo = QComboBox()
        existing_bids = {sl.band_layout_id for sl, _ in list_song_layouts_for_song(app_state.conn, song_id)}
        for layout_id, _layout_name, band_name in list_all_band_layouts(app_state.conn):
            if song_layout_id:
                # Edit mode: show all band layouts
                self.band_layout_combo.addItem(band_name, layout_id)
            elif layout_id not in existing_bids:
                # New mode: only show band layouts that don't already have a song layout
                self.band_layout_combo.addItem(band_name, layout_id)
        self.band_layout_combo.currentIndexChanged.connect(self._on_band_layout_changed)

        if band_layout_id:
            for i in range(self.band_layout_combo.count()):
                if self.band_layout_combo.itemData(i) == band_layout_id:
                    self.band_layout_combo.setCurrentIndex(i)
                    break
        if song_layout_id:
            self.band_layout_combo.setEnabled(False)

        layout.addWidget(self.band_layout_combo)

        self.assignment_panel = SongLayoutAssignmentPanel(app_state, self)
        self.assignment_panel.assignment_changed.connect(self._on_assignment_changed)
        layout.addWidget(self.assignment_panel, 1)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self.accept)
        btn_layout.addWidget(save_btn)
        layout.addLayout(btn_layout)

        self._on_band_layout_changed()

    def _on_assignment_changed(self) -> None:
        if self._song_layout_id:
            self.song_layout_updated.emit(self._song_layout_id)

    def _on_band_layout_changed(self) -> None:
        bid = self.band_layout_combo.currentData()
        if not bid:
            self.assignment_panel.clear()
            return
        if self._song_layout_id:
            self.assignment_panel.refresh(
                band_layout_id=bid,
                song_layout_id=self._song_layout_id,
                parts_json=self.parts_json,
            )
        else:
            song_layout_id = get_or_create_song_layout_for_band(
                self.app_state.conn, self.song_id, bid
            )
            self._song_layout_id = song_layout_id
            self.assignment_panel.refresh(
                band_layout_id=bid,
                song_layout_id=song_layout_id,
                parts_json=self.parts_json,
            )
