#!/usr/bin/env python3
"""
ABC Music Manager — entry point.
"""

import multiprocessing
import sys
from pathlib import Path

# Allow running from repo root without installing package
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from PySide6.QtWidgets import QApplication

from abc_music_manager.app_icon import application_icon
from abc_music_manager.services.app_state import AppState
from abc_music_manager.services.preferences import ensure_default_lotro_root
from abc_music_manager.ui.theme import apply_theme
from abc_music_manager.ui.main_window import MainWindow


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("ABC Music Manager")
    icon = application_icon()
    if not icon.isNull():
        app.setWindowIcon(icon)
    apply_theme(app)
    ensure_default_lotro_root()
    with AppState() as state:
        window = MainWindow(state)
        if not icon.isNull():
            window.setWindowIcon(icon)
        window.show()
        app.aboutToQuit.connect(window.playback_state.close)
        sys.exit(app.exec())


if __name__ == "__main__":
    multiprocessing.freeze_support()  # Required for PyInstaller on Windows: child runs target, not main()
    main()
