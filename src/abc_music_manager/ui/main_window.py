"""
Main window: menu bar, navigation (Library | Setlists | Bands | Set Playback | Settings), stacked pages.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QStackedWidget,
    QSplitter,
    QHBoxLayout,
    QLabel,
    QMenu,
    QMessageBox,
    QApplication,
    QListWidget,
    QListWidgetItem,
)
from PySide6.QtCore import Qt, QByteArray
from PySide6.QtGui import QColor, QFontMetrics, QPalette

from ..services.app_state import AppState
from ..services import preferences
from ..services.preferences import get_splitter_state, set_splitter_state


def _restore_window_geometry(window: QMainWindow) -> None:
    """Restore main window size and position from preferences if available."""
    geom_b64 = preferences.get_window_geometry()
    if not geom_b64:
        return
    data = QByteArray.fromBase64(geom_b64.encode("utf-8"))
    if data.isEmpty():
        return
    window.restoreGeometry(data)


def _save_window_geometry(window: QMainWindow) -> None:
    """Persist main window size and position to preferences."""
    data = window.saveGeometry()
    if data.isEmpty():
        return
    preferences.set_window_geometry(data.toBase64().data().decode("utf-8"))


class PlaceholderPage(QWidget):
    """Placeholder content for a section."""

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(title))
        layout.addStretch()


class MainWindow(QMainWindow):
    """Main application window with navigation and stacked content."""

    PAGES = ["Library", "Setlists", "Bands", "Set Playback", "Settings"]

    def __init__(self, app_state: AppState) -> None:
        super().__init__()
        self.app_state = app_state
        self.setWindowTitle("ABC Music Manager")
        self.setMinimumSize(900, 600)
        self.resize(1000, 700)
        _restore_window_geometry(self)

        self._build_menu_bar()
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)

        self.stacked = QStackedWidget()
        self.stacked.setObjectName("main_content")
        from .library_view import LibraryView
        from .setlists_view import SetlistsView
        from .bands_view import BandsView
        from .set_playback_view import SetPlaybackView
        from .settings_view import SettingsView
        self.library_view = LibraryView(app_state)
        self.setlists_view = SetlistsView(app_state)
        self.stacked.addWidget(self.library_view)
        self.stacked.addWidget(self.setlists_view)
        self.stacked.addWidget(BandsView(app_state))
        self.stacked.addWidget(SetPlaybackView(app_state))
        self.stacked.addWidget(SettingsView(app_state))
        self.library_view.navigateToSetlist.connect(self._on_navigate_to_setlist)

        self.nav_list = QListWidget()
        self.nav_list.setObjectName("nav_list")
        self.nav_list.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        # Force selection palette to theme colors so platform default (e.g. golden) never appears
        from .theme import COLOR_SURFACE, COLOR_TEXT_HEADER
        pal = self.nav_list.palette()
        pal.setColor(QPalette.ColorRole.Highlight, QColor(COLOR_SURFACE))
        pal.setColor(QPalette.ColorRole.HighlightedText, QColor(COLOR_TEXT_HEADER))
        self.nav_list.setPalette(pal)
        for name in self.PAGES:
            self.nav_list.addItem(QListWidgetItem(name))
        self.nav_list.setCurrentRow(0)
        self.nav_list.currentRowChanged.connect(self.stacked.setCurrentIndex)
        # Nav list width: default to fit content (text + padding); user can resize via splitter
        fm = QFontMetrics(self.nav_list.font())
        text_width = max(fm.horizontalAdvance(name) for name in self.PAGES)
        self._nav_preferred_width = text_width + 32
        self.nav_list.setMinimumWidth(self._nav_preferred_width)
        self.nav_list.setMaximumWidth(400)

        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.addWidget(self.nav_list)
        self._splitter.addWidget(self.stacked)
        self._splitter.setStretchFactor(1, 1)
        main_layout.addWidget(self._splitter)
        self._splitter_initial_sizes_set = False

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not getattr(self, "_splitter_initial_sizes_set", True):
            self._splitter_initial_sizes_set = True
            saved = get_splitter_state()
            if saved:
                data = QByteArray.fromBase64(saved.encode("utf-8"))
                if not data.isEmpty() and self._splitter.restoreState(data):
                    return
            total = self._splitter.width()
            handle_w = self._splitter.handleWidth()
            nav_w = min(self._nav_preferred_width, max(self.nav_list.minimumWidth(), total - handle_w - 100))
            self._splitter.setSizes([nav_w, total - nav_w - handle_w])

    def closeEvent(self, event) -> None:
        _save_window_geometry(self)
        data = self._splitter.saveState()
        if not data.isEmpty():
            set_splitter_state(data.toBase64().data().decode("utf-8"))
        super().closeEvent(event)

    def _build_menu_bar(self) -> None:
        menubar = self.menuBar()
        file_menu = menubar.addMenu("&File")
        file_menu.addAction("Scan &Library", self._on_scan_library)
        file_menu.addAction("&Settings", self._on_settings)
        file_menu.addAction("Write &PluginData...", self._on_write_plugindata)
        file_menu.addSeparator()
        file_menu.addAction("E&xit", QApplication.quit)
        view_menu = menubar.addMenu("&View")
        for i, name in enumerate(self.PAGES):
            view_menu.addAction(name, lambda checked=False, idx=i: self._go_to_page(idx))
        help_menu = menubar.addMenu("&Help")
        help_menu.addAction("&About", self._on_about)

    def _on_tab_changed(self, index: int) -> None:
        self.stacked.setCurrentIndex(index)

    def _go_to_page(self, index: int) -> None:
        self.nav_list.setCurrentRow(index)
        self.stacked.setCurrentIndex(index)

    def _on_navigate_to_setlist(self, setlist_id: int) -> None:
        self._go_to_page(self.PAGES.index("Setlists"))
        self.setlists_view.select_setlist_by_id(setlist_id)

    def _on_scan_library(self) -> None:
        from ..scanning.scanner import run_scan
        from .duplicate_dialog import show_duplicate_resolution

        def on_duplicate(conn, new_file_path, parsed, existing_song_ids):
            return show_duplicate_resolution(
                conn, new_file_path, parsed.title, existing_song_ids
            )

        self.statusBar().showMessage("Scanning...")
        QApplication.processEvents()
        try:
            total, scanned, errors = run_scan(
                self.app_state.conn,
                progress_callback=lambda i, n: self.statusBar().showMessage(f"Scanning {i}/{n}..."),
                on_duplicate=on_duplicate,
            )
            self.statusBar().showMessage(f"Scan complete: {scanned} scanned, {errors} errors.")
            QMessageBox.information(
                self,
                "Scan complete",
                f"Found {total} .abc files.\nScanned: {scanned}\nErrors: {errors}",
            )
        except Exception as e:
            self.statusBar().showMessage("Scan failed.")
            QMessageBox.critical(self, "Scan failed", str(e))
        else:
            self.library_view.refresh()

    def _on_settings(self) -> None:
        self._go_to_page(self.PAGES.index("Settings"))

    def _on_write_plugindata(self) -> None:
        from ..services.plugindata_writer import write_plugindata_all_targets
        try:
            success, errors = write_plugindata_all_targets(self.app_state.conn)
            if errors:
                QMessageBox.warning(
                    self,
                    "PluginData write",
                    f"Written to {success} target(s).\nErrors:\n" + "\n".join(errors),
                )
            else:
                QMessageBox.information(
                    self,
                    "PluginData write",
                    f"Written to {success} target(s).",
                )
        except Exception as e:
            QMessageBox.critical(self, "PluginData write failed", str(e))

    def _on_about(self) -> None:
        QMessageBox.about(
            self,
            "About ABC Music Manager",
            "ABC Music Manager\n\nLocal-first desktop app for ABC music library and setlist management.",
        )
