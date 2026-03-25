"""Locate and load the application window icon (repo checkout or PyInstaller bundle)."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtGui import QIcon


def _bundle_root() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    # src/abc_music_manager/app_icon.py -> repo root
    return Path(__file__).resolve().parents[2]


def application_icon() -> QIcon:
    """Return a multi-resolution icon for the main window and taskbar/dock."""
    base = _bundle_root() / "resources" / "icons"
    icon = QIcon()
    ico = base / "app.ico"
    if ico.is_file():
        icon.addFile(str(ico))
    # Explicit sizes help some platforms pick a crisp pixmap
    if base.is_dir():
        for name in ("512", "256", "128", "64", "48", "32", "16"):
            png = base / f"app_{name}.png"
            if png.is_file():
                icon.addFile(str(png))
    return icon
