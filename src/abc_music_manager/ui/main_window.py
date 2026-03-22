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
from PySide6.QtCore import Qt, QByteArray, QRect, QTimer, QEvent
from PySide6.QtGui import QColor, QFontMetrics, QPalette

from ..services.app_state import AppState
from ..services import preferences
from ..services.playback_state import PlaybackState, PlaylistEntry
from ..services.preferences import (
    get_splitter_state,
    set_splitter_state,
    set_bands_splitter_state,
    set_setlists_splitter_state,
    set_setlists_editor_splitter_state,
)


def _restore_window_geometry(window: QMainWindow) -> None:
    """Restore main window size and position from preferences if available."""
    saved = preferences.get_window_geometry()
    if not saved:
        return
    if isinstance(saved, dict):
        # Human-readable format: {x, y, width, height, maximized}
        x = saved.get("x", 0)
        y = saved.get("y", 0)
        w = saved.get("width", 1000)
        h = saved.get("height", 700)
        window.setGeometry(QRect(x, y, w, h))
        if saved.get("maximized"):
            window.setWindowState(window.windowState() | Qt.WindowState.WindowMaximized)
    else:
        # Legacy base64 format
        data = QByteArray.fromBase64(saved.encode("utf-8"))
        if not data.isEmpty():
            window.restoreGeometry(data)


def _save_window_geometry(window: QMainWindow) -> None:
    """Persist main window size and position to preferences (human-readable format)."""
    # Use normalGeometry when maximized so we get the size/position when un-maximized
    geom = window.normalGeometry() if (window.windowState() & Qt.WindowState.WindowMaximized) else window.geometry()
    maximized = bool(window.windowState() & Qt.WindowState.WindowMaximized)
    preferences.set_window_geometry({
        "x": geom.x(),
        "y": geom.y(),
        "width": geom.width(),
        "height": geom.height(),
        "maximized": maximized,
    })


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
        from ..services.band_layout_pan_service import get_part_pan_map
        self.playback_state = PlaybackState(
            self,
            get_part_pan_map=lambda sl_id, bl_id, setlist_item_id=None: get_part_pan_map(
                app_state.conn, sl_id, bl_id, setlist_item_id
            ),
        )
        self.playback_state.soundfont_missing.connect(self._on_soundfont_missing)
        self.playback_state.playback_failed.connect(self._on_playback_failed)
        self.playback_state.layout_used.connect(self._on_layout_used)
        self.playback_state.state_changed.connect(self._update_window_title)
        self._update_window_title()
        self.setMinimumSize(900, 600)
        self.resize(1000, 700)
        _restore_window_geometry(self)

        self._build_menu_bar()
        from .playback_toolbar import PlaybackToolbar
        self._playback_toolbar = PlaybackToolbar(
            self.playback_state, self, app_state=app_state
        )
        self.addToolBar(self._playback_toolbar)
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
        self.library_view = LibraryView(app_state, self.playback_state)
        self.setlists_view = SetlistsView(app_state, self.playback_state)
        self.bands_view = BandsView(app_state)
        self.stacked.addWidget(self.library_view)
        self.stacked.addWidget(self.setlists_view)
        self.stacked.addWidget(self.bands_view)
        self.stacked.addWidget(SetPlaybackView(app_state, self.playback_state))
        self.stacked.addWidget(SettingsView(app_state, self.playback_state))
        self.library_view.navigateToSetlist.connect(self._on_navigate_to_setlist)
        self._playback_toolbar.playlistExportedAsSet.connect(self._on_navigate_to_setlist)
        self.bands_view.band_layout_updated.connect(self._on_band_layout_updated)

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
        self.nav_list.currentRowChanged.connect(self._on_nav_row_changed)
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

        self._geometry_save_timer = QTimer(self)
        self._geometry_save_timer.setSingleShot(True)
        self._geometry_save_timer.timeout.connect(lambda: _save_window_geometry(self))
        self._splitter_save_timer = QTimer(self)
        self._splitter_save_timer.setSingleShot(True)
        self._splitter_save_timer.timeout.connect(lambda: set_splitter_state(self._splitter.sizes()))
        self._splitter.splitterMoved.connect(lambda: self._splitter_save_timer.start(150))
        self._skip_save_on_exit = False

    def _disable_saving_and_prepare_restart(self) -> None:
        """Disable all preference saving on exit (used when restarting after reset)."""
        from ..services import preferences as prefs_module

        self._skip_save_on_exit = True
        prefs_module.set_skip_all_saves(True)
        self._geometry_save_timer.stop()
        self._splitter_save_timer.stop()
        self.bands_view._bands_splitter_save_timer.stop()
        self.setlists_view._songs_header_save_timer.stop()
        self.setlists_view._top_split_save_timer.stop()
        self.setlists_view._setlists_splitter_save_timer.stop()
        self.setlists_view._editor_splitter_save_timer.stop()
        self.library_view._header_save_timer.stop()
        if hasattr(self._playback_toolbar, "_parts_playlist_save_timer"):
            self._playback_toolbar._parts_playlist_save_timer.stop()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, "_geometry_save_timer"):
            self._geometry_save_timer.start(150)

    def moveEvent(self, event) -> None:
        super().moveEvent(event)
        if hasattr(self, "_geometry_save_timer"):
            self._geometry_save_timer.start(150)

    def changeEvent(self, event: QEvent) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange and hasattr(self, "_geometry_save_timer"):
            self._geometry_save_timer.start(150)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not getattr(self, "_splitter_initial_sizes_set", True):
            self._splitter_initial_sizes_set = True
            saved = get_splitter_state()
            if saved:
                if isinstance(saved, list) and len(saved) >= 2:
                    self._splitter.setSizes(saved)
                    return
                # Legacy base64 format
                data = QByteArray.fromBase64(saved.encode("utf-8"))
                if not data.isEmpty() and self._splitter.restoreState(data):
                    return
            total = self._splitter.width()
            handle_w = self._splitter.handleWidth()
            nav_w = min(self._nav_preferred_width, max(self.nav_list.minimumWidth(), total - handle_w - 100))
            self._splitter.setSizes([nav_w, total - nav_w - handle_w])

    def closeEvent(self, event) -> None:
        if not self._confirm_leave_page_with_unsaved(-1):
            event.ignore()
            return
        self.playback_state.close()
        if not self._skip_save_on_exit:
            _save_window_geometry(self)
            set_splitter_state(self._splitter.sizes())
            set_bands_splitter_state(self.bands_view.bands_splitter.sizes())
            set_setlists_splitter_state(self.setlists_view.setlists_splitter.sizes())
            set_setlists_editor_splitter_state(self.setlists_view.editor_splitter.sizes())
            self.setlists_view._save_setlists_state()
            self.library_view._save_library_table_header_state()
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

    def _page_has_unsaved_changes(self, page_index: int) -> bool:
        """Return True if the page at index has unsaved changes."""
        widget = self.stacked.widget(page_index)
        if hasattr(widget, "has_unsaved_changes") and callable(widget.has_unsaved_changes):
            return widget.has_unsaved_changes()
        return False

    def _confirm_leave_page_with_unsaved(self, target_index: int) -> bool:
        """Return True if the user confirms leaving (or no unsaved changes)."""
        current = self.stacked.currentIndex()
        if current == target_index:
            return True
        if not self._page_has_unsaved_changes(current):
            return True
        reply = QMessageBox.question(
            self,
            "Unsaved changes",
            "You have unsaved changes. Are you sure you want to leave?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return reply == QMessageBox.StandardButton.Yes

    def _on_nav_row_changed(self, row: int) -> None:
        if row < 0:
            return
        if not self._confirm_leave_page_with_unsaved(row):
            self.nav_list.blockSignals(True)
            self.nav_list.setCurrentRow(self.stacked.currentIndex())
            self.nav_list.blockSignals(False)
            return
        self.stacked.setCurrentIndex(row)

    def _go_to_page(self, index: int) -> None:
        if not self._confirm_leave_page_with_unsaved(index):
            return
        self.nav_list.setCurrentRow(index)
        self.stacked.setCurrentIndex(index)

    def _on_navigate_to_setlist(self, setlist_id: int) -> None:
        self._go_to_page(self.PAGES.index("Setlists"))
        self.setlists_view.select_setlist_by_id(setlist_id)

    def _on_band_layout_updated(self, band_layout_id: int) -> None:
        """When a band layout's slots change, restart playback if it's the active layout."""
        if self.playback_state.get_active_band_layout_id() == band_layout_id:
            self.playback_state.restart_current_with_new_stereo()

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
        from .plugindata_export_dialog import PlugindataExportDialog
        dlg = PlugindataExportDialog(self.app_state.conn, self)
        dlg.exec()

    def _update_window_title(self) -> None:
        """Set window title to include currently playing song when applicable."""
        base = "ABC Music Manager"
        ps = self.playback_state
        if ps.playlist and 0 <= ps.current_index < len(ps.playlist):
            entry = ps.playlist[ps.current_index]
            sub = self._format_title_bar_song(entry)
            if sub:
                if ps.is_playing:
                    self.setWindowTitle(f"{base} — Now Playing: {sub}")
                elif ps.is_paused:
                    self.setWindowTitle(f"{base} — Paused: {sub}")
                else:
                    self.setWindowTitle(f"{base} — {sub}")
            else:
                self.setWindowTitle(f"{base} — {entry.title}")
        else:
            self.setWindowTitle(base)

    def _format_title_bar_song(self, entry: PlaylistEntry) -> str:
        """Format current song as 'Song Name - Composer (duration) [# Parts]' for title bar."""
        from ..db.library_query import get_song_for_detail, get_song_id_for_file_path

        sid = entry.song_id or (
            get_song_id_for_file_path(self.app_state.conn, entry.file_path) if self.app_state else None
        )
        detail = get_song_for_detail(self.app_state.conn, sid) if (self.app_state and sid) else None
        name = entry.title or "Unknown"
        composer = (detail.get("composers") or "").strip() if detail else ""
        duration_sec = detail.get("duration_seconds") if detail else None
        part_count = detail.get("part_count", 0) if detail else 0

        def _fmt_dur(s):
            if s is None or s < 0:
                return ""
            m, s = int(s // 60), int(s % 60)
            return f"{m}:{s:02d}" if m > 0 else f"0:{s:02d}"

        parts = f"[{part_count} Parts]"
        out = name
        if composer:
            out += f" - {composer}"
        if duration_sec is not None and duration_sec >= 0:
            out += f" ({_fmt_dur(duration_sec)})"
        out += f" {parts}"
        return out

    def _on_playback_failed(self, message: str) -> None:
        """Show error when ABC-to-MIDI conversion fails."""
        QMessageBox.warning(self, "Playback Error", message)

    def _on_soundfont_missing(self) -> None:
        """Show dialog when soundfont is not found. User can locate or download."""
        from .soundfont_dialog import show_soundfont_dialog
        show_soundfont_dialog(self)

    def _on_layout_used(
        self, song_id: int, band_layout_id: int, song_layout_id: int, setlist_item_id: object
    ) -> None:
        """Update song's last-used layout when playback starts with a layout."""
        from ..db.song_repo import update_song_last_layout
        update_song_last_layout(
            self.app_state.conn, song_id, band_layout_id, song_layout_id,
            setlist_item_id if isinstance(setlist_item_id, int) else None,
        )

    def _on_about(self) -> None:
        QMessageBox.about(
            self,
            "About ABC Music Manager",
            "ABC Music Manager\n\nLocal-first desktop app for ABC music library and setlist management.",
        )
