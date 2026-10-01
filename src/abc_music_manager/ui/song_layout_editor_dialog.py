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
from ..services.preferences import (
    SONG_LAYOUT_EDITOR_DIALOG_MIN_HEIGHT,
    SONG_LAYOUT_EDITOR_DIALOG_MIN_WIDTH,
    get_song_layout_editor_dialog_size,
    set_song_layout_editor_dialog_size,
)
from ..db.band_repo import list_all_band_layouts, list_layout_slots
from ..db.song_layout_repo import (
    list_song_layouts_for_song,
    get_or_create_song_layout_for_band,
)
from .band_layout_grid import CARD_HEIGHT, CARD_WIDTH, PIXELS_PER_UNIT
from .dialog_size import RememberDialogSize, layout_editor_size_for_slots, restore_dialog_size
from .song_layout_assignment_panel import SongLayoutAssignmentPanel


class SongLayoutEditorDialog(RememberDialogSize, QDialog):
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
        # Floor fits 6 cards wide × 3 cards deep. Larger layouts grow on first open.
        self.setMinimumSize(SONG_LAYOUT_EDITOR_DIALOG_MIN_WIDTH, SONG_LAYOUT_EDITOR_DIALOG_MIN_HEIGHT)

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
        saved = get_song_layout_editor_dialog_size()
        default_w, default_h = self._default_size()
        self._begin_size_memory(
            saved,
            default_w,
            default_h,
            set_song_layout_editor_dialog_size,
        )

    def _default_size(self) -> tuple[int, int]:
        """Fit the selected band's cards, and never start smaller than the 6×3 floor."""
        band_layout_id = self.band_layout_combo.currentData()
        positions: list[tuple[int, int]] = []
        if band_layout_id:
            positions = [(s.x, s.y) for s in list_layout_slots(self.app_state.conn, band_layout_id)]
        return layout_editor_size_for_slots(
            positions,
            card_width=CARD_WIDTH,
            card_height=CARD_HEIGHT,
            pixels_per_unit=PIXELS_PER_UNIT,
            floor_width=SONG_LAYOUT_EDITOR_DIALOG_MIN_WIDTH,
            floor_height=SONG_LAYOUT_EDITOR_DIALOG_MIN_HEIGHT,
        )

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
        self._refit_until_user_resizes()

    def _refit_until_user_resizes(self) -> None:
        """Grow to the current band until a saved size, or a manual resize, takes over."""
        if get_song_layout_editor_dialog_size() is not None:
            return
        if getattr(self, "_dialog_size_user_resized", False):
            return
        if not getattr(self, "_dialog_size_ready", False):
            return
        width, height = self._default_size()
        self._dialog_size_ready = False
        restore_dialog_size(self, None, width, height)
        self._dialog_size_ready = True
