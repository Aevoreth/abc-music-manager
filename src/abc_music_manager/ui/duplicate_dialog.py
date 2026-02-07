"""
Duplicate resolution dialog: when two primary-library files share logical identity.
DECISIONS 011: (a) treat as same song variant, (b) keep as separate songs, (c) ignore one file.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QLabel,
    QPushButton,
    QButtonGroup,
    QRadioButton,
    QComboBox,
    QDialogButtonBox,
)
from PySide6.QtCore import Qt

from ..db.library_query import get_primary_file_path_for_song


def show_duplicate_resolution(
    conn,
    new_file_path: str,
    parsed_title: str,
    existing_song_ids: list[int],
) -> tuple[str, int | None]:
    """
    Show dialog and return ("link", song_id) or ("separate", None) or ("ignore", None).
    """
    dlg = DuplicateResolutionDialog(conn, new_file_path, parsed_title, existing_song_ids)
    if dlg.exec() != QDialog.DialogCode.Accepted:
        return ("ignore", None)
    return dlg.get_result()


class DuplicateResolutionDialog(QDialog):
    def __init__(self, conn, new_file_path: str, parsed_title: str, existing_song_ids: list[int]) -> None:
        super().__init__()
        self.conn = conn
        self.new_file_path = new_file_path
        self.existing_song_ids = existing_song_ids
        self.setWindowTitle("Duplicate song detected")
        layout = QVBoxLayout(self)

        existing_path = ""
        if existing_song_ids:
            existing_path = get_primary_file_path_for_song(conn, existing_song_ids[0]) or "(unknown)"

        layout.addWidget(QLabel(
            f"Another file in your library has the same identity (title, composer, part count) as this one."
        ))
        layout.addWidget(QLabel(f"Existing: {existing_path}"))
        layout.addWidget(QLabel(f"New file: {new_file_path}"))
        layout.addWidget(QLabel("How do you want to handle the new file?"))

        self.link_radio = QRadioButton("Link to existing song (treat as variant)")
        self.separate_radio = QRadioButton("Keep as separate song")
        self.ignore_radio = QRadioButton("Ignore this file (do not index)")
        self.link_radio.setChecked(True)
        layout.addWidget(self.link_radio)
        layout.addWidget(self.separate_radio)
        layout.addWidget(self.ignore_radio)

        if len(existing_song_ids) > 1:
            layout.addWidget(QLabel("Link to which existing song?"))
            self.song_combo = QComboBox()
            for sid in existing_song_ids:
                path = get_primary_file_path_for_song(conn, sid) or f"Song id {sid}"
                self.song_combo.addItem(path, sid)
            layout.addWidget(self.song_combo)
        else:
            self.song_combo = None

        bbox = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        bbox.accepted.connect(self.accept)
        bbox.rejected.connect(self.reject)
        layout.addWidget(bbox)

    def get_result(self) -> tuple[str, int | None]:
        if self.ignore_radio.isChecked():
            return ("ignore", None)
        if self.separate_radio.isChecked():
            return ("separate", None)
        if self.link_radio.isChecked() and self.song_combo is not None:
            return ("link", self.song_combo.currentData())
        if self.link_radio.isChecked() and self.existing_song_ids:
            return ("link", self.existing_song_ids[0])
        return ("ignore", None)
