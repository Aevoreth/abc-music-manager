"""
Dialog when soundfont is not found: locate existing file or download.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFileDialog,
    QProgressDialog,
    QMessageBox,
)
from PySide6.QtCore import Qt

from ..playback import resolve_soundfont_path, download_soundfont
from ..playback.soundfont_resolver import get_download_target_dir
from ..services import preferences


def show_soundfont_dialog(parent) -> bool:
    """
    Show dialog to locate or download soundfont.
    Returns True if soundfont is now available, False otherwise.
    """
    dlg = SoundfontDialog(parent)
    dlg.exec()
    return resolve_soundfont_path(preferences.get_playback_soundfont_path()) is not None


class SoundfontDialog(QDialog):
    """Locate or download LotroInstruments soundfont."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Soundfont Required")
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            "The LotroInstruments soundfont is required for playback.\n"
            "Choose an option below:"
        ))
        btn_layout = QHBoxLayout()
        locate_btn = QPushButton("Locate...")
        locate_btn.clicked.connect(self._on_locate)
        download_btn = QPushButton("Download")
        download_btn.clicked.connect(self._on_download)
        btn_layout.addWidget(locate_btn)
        btn_layout.addWidget(download_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)

    def _on_locate(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select LotroInstruments Soundfont",
            "",
            "SoundFont (*.sf2);;All Files (*)",
        )
        if path:
            preferences.set_playback_soundfont_path(path)
            if resolve_soundfont_path(path):
                QMessageBox.information(self, "Success", "Soundfont located successfully.")
                self.accept()
            else:
                QMessageBox.warning(
                    self,
                    "Invalid",
                    "The selected file could not be used. Please select a valid LotroInstruments .sf2 file.",
                )

    def _on_download(self) -> None:
        target_dir = get_download_target_dir()
        progress = QProgressDialog("Downloading soundfont...", "Cancel", 0, 0, self)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.show()

        def on_progress(current: int, total: int) -> None:
            if total > 0:
                progress.setMaximum(total)
                progress.setValue(current)
            QApplication.processEvents()

        try:
            result = download_soundfont(
                target_dir=target_dir,
                progress_callback=on_progress,
            )
        except Exception as e:
            progress.close()
            QMessageBox.critical(
                self,
                "Download Failed",
                f"Failed to download soundfont: {e}",
            )
            return
        progress.close()

        if result:
            preferences.set_playback_soundfont_path("")  # Use default lookup
            QMessageBox.information(
                self,
                "Success",
                f"Soundfont downloaded to:\n{result}",
            )
            self.accept()
        else:
            QMessageBox.warning(
                self,
                "Download Failed",
                "Could not download or verify the soundfont.",
            )
