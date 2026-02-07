"""
Main window: menu bar, navigation (Library | Setlists | Bands | Set Playback | Settings), stacked pages.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QStackedWidget,
    QHBoxLayout,
    QLabel,
    QMenu,
    QMessageBox,
    QApplication,
    QListWidget,
    QListWidgetItem,
)
from PySide6.QtCore import Qt

from ..services.app_state import AppState


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

        self._build_menu_bar()
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)

        self.stacked = QStackedWidget()
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
        main_layout.addWidget(self.stacked, 1)
        self.library_view.navigateToSetlist.connect(self._on_navigate_to_setlist)

        self.nav_list = QListWidget()
        self.nav_list.setMaximumWidth(160)
        self.nav_list.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        for name in self.PAGES:
            self.nav_list.addItem(QListWidgetItem(name))
        self.nav_list.currentRowChanged.connect(self.stacked.setCurrentIndex)
        main_layout.insertWidget(0, self.nav_list)

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
