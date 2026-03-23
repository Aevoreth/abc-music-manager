"""
Dialog that displays the README (User Guide) with Markdown rendering.
"""

from __future__ import annotations

import sys
from html import escape
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices, QTextDocument
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
)


def _get_doc_base_path() -> Path | None:
    """Return the directory containing README.md and related docs. Works when running from source or PyInstaller frozen."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    base = Path(__file__).resolve().parents[3]
    return base


def _get_readme_path() -> Path | None:
    """Return path to README.md."""
    base = _get_doc_base_path()
    return (base / "README.md") if base else None


class _UserGuideBrowser(QTextBrowser):
    """QTextBrowser that loads local docs (LICENSE, NOTICE, DEVELOPER.md, etc.) and opens external links in the system browser."""

    def __init__(self, base_path: Path, readme_url: QUrl, parent=None):
        super().__init__(parent)
        self._base_path = Path(base_path).resolve()
        self._readme_url = readme_url
        self._back_stack: list[dict] = []
        self._forward_stack: list[dict] = []
        self._current: dict | None = None  # {"url": QUrl} or {"html": str}
        self._history_changed = lambda: None
        self.setOpenLinks(False)
        self.setOpenExternalLinks(False)
        self.anchorClicked.connect(self._on_anchor_clicked)

    def _on_anchor_clicked(self, url: QUrl) -> None:
        scheme = url.scheme().lower() if url.scheme() else ""
        if scheme in ("http", "https"):
            QDesktopServices.openUrl(url)
            return
        path = self._resolve_url_to_path(url)
        if path and path.is_file() and self._is_path_allowed(path):
            self._load_local_file(path)
        elif url.isLocalFile():
            # Invalid or missing local file - do not try to open externally
            pass
        else:
            QDesktopServices.openUrl(url)

    def _is_path_allowed(self, path: Path) -> bool:
        try:
            path.resolve().relative_to(self._base_path)
        except ValueError:
            return False
        return True

    def _resolve_url_to_path(self, url: QUrl) -> Path | None:
        if url.isLocalFile():
            p = Path(url.toLocalFile()).resolve()
            if p.is_file() and self._is_path_allowed(p):
                return p
            # Fallback: path may be wrongly resolved (e.g. base one level too high).
            # Try finding the file by name under base_path.
            for base in (self._base_path, self._base_path / "docs"):
                fallback = base / p.name
                if fallback.is_file() and self._is_path_allowed(fallback):
                    return fallback
            return None
        path_str = url.path()
        if not path_str:
            return None
        p = Path(path_str)
        if p.is_absolute():
            return p if p.is_file() and self._is_path_allowed(p) else None
        for base in (self._base_path, self._base_path / "docs"):
            resolved = (base / p).resolve()
            if resolved.is_file() and self._is_path_allowed(resolved):
                return resolved
        return None

    def set_initial_state(self) -> None:
        """Call after initial setSource(readme_url) to record the home state."""
        self._current = {"url": self._readme_url}

    def _push_back_and_clear_forward(self) -> None:
        """Push current document to back stack for navigation."""
        self._forward_stack.clear()
        if self._current:
            self._back_stack.append(self._current.copy())
        self._history_changed()

    def _load_local_file(self, path: Path) -> None:
        self._push_back_and_clear_forward()
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            self._back_stack.pop()
            return
        if path.suffix.lower() == ".md":
            doc = QTextDocument()
            doc.setMarkdown(text)
            html = doc.toHtml()
        else:
            html = f"<pre>{escape(text)}</pre>"
        dir_url = QUrl.fromLocalFile(str(path.parent.resolve()) + "/")
        self.setHtml(html)
        self.document().setBaseUrl(dir_url)
        self._current = {"html": html, "base": dir_url}
        self._history_changed()

    def _go_back(self) -> None:
        if not self._back_stack:
            return
        self._forward_stack.append(self._current.copy() if self._current else {})
        entry = self._back_stack.pop()
        self._restore_state(entry)
        self._current = entry
        self._history_changed()

    def _go_forward(self) -> None:
        if not self._forward_stack:
            return
        self._back_stack.append(self._current.copy() if self._current else {})
        entry = self._forward_stack.pop()
        self._restore_state(entry)
        self._current = entry
        self._history_changed()

    def _restore_state(self, entry: dict) -> None:
        if "url" in entry:
            self.setSource(entry["url"])
        else:
            self.setHtml(entry["html"])
            if "base" in entry:
                self.document().setBaseUrl(entry["base"])

    def is_backward_available(self) -> bool:
        return len(self._back_stack) > 0

    def is_forward_available(self) -> bool:
        return len(self._forward_stack) > 0


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

    base_path = path.parent
    dlg = QDialog(parent)
    dlg.setWindowTitle(f"ABC Music Manager — User Guide (v{__version__})")
    dlg.setMinimumSize(520, 400)
    dlg.resize(640, 520)

    layout = QVBoxLayout(dlg)
    readme_url = QUrl.fromLocalFile(str(path))
    browser = _UserGuideBrowser(base_path, readme_url)
    browser.setSearchPaths([str(base_path), str(base_path / "docs")])

    browser.setSource(readme_url)
    browser.set_initial_state()

    back_btn = QPushButton("← Back")
    forward_btn = QPushButton("Forward →")
    home_btn = QPushButton("User Guide")

    def update_nav_buttons() -> None:
        back_btn.setEnabled(browser.is_backward_available())
        forward_btn.setEnabled(browser.is_forward_available())

    browser._history_changed = update_nav_buttons
    back_btn.clicked.connect(browser._go_back)
    forward_btn.clicked.connect(browser._go_forward)
    def go_home() -> None:
        while browser.is_backward_available():
            browser._go_back()
        update_nav_buttons()
    home_btn.clicked.connect(go_home)

    nav_layout = QHBoxLayout()
    nav_layout.addWidget(back_btn)
    nav_layout.addWidget(forward_btn)
    nav_layout.addWidget(home_btn)
    nav_layout.addStretch()
    layout.addLayout(nav_layout)
    layout.addWidget(browser)

    btn_layout = QHBoxLayout()
    btn_layout.addStretch()
    close_btn = QPushButton("Close")
    close_btn.clicked.connect(dlg.accept)
    btn_layout.addWidget(close_btn)
    layout.addLayout(btn_layout)

    dlg.exec()
