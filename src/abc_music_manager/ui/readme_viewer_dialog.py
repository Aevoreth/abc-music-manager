"""
Dialog that displays the README (User Guide) with Markdown rendering.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
)


def _get_readme_path() -> Path | None:
    """Return path to README.md. Works when running from source or PyInstaller frozen."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "README.md"
    # Running from source: from ui/readme_viewer_dialog.py up to repo root
    base = Path(__file__).resolve().parents[3]
    return base / "README.md"


def open_readme_viewer(parent=None) -> None:
    """Open a modal dialog displaying the README (User Guide)."""
    from ..version import __version__

    path = _get_readme_path()
    if not path or not path.is_file():
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.information(
            parent,
            "User Guide",
            "User Guide not found. See the repository README.",
        )
        return

    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.warning(
            parent,
            "User Guide",
            "Could not read User Guide.",
        )
        return

    dlg = QDialog(parent)
    dlg.setWindowTitle(f"ABC Music Manager — User Guide (v{__version__})")
    dlg.setMinimumSize(520, 400)
    dlg.resize(640, 520)

    layout = QVBoxLayout(dlg)
    browser = QTextBrowser()
    browser.setMarkdown(content)
    browser.setOpenExternalLinks(True)
    layout.addWidget(browser)

    btn_layout = QHBoxLayout()
    btn_layout.addStretch()
    close_btn = QPushButton("Close")
    close_btn.clicked.connect(dlg.accept)
    btn_layout.addWidget(close_btn)
    layout.addLayout(btn_layout)

    dlg.exec()
