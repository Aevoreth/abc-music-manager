"""
Main window: menu bar, navigation (Library | Setlists | Bands | Settings), stacked pages.
"""

from __future__ import annotations

import base64

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
from PySide6.QtGui import QColor, QFontMetrics, QGuiApplication, QPalette

from ..services.app_state import AppState
from ..services import preferences
from ..services.playback_state import PlaybackState, PlaylistEntry
from ..services.preferences import (
    DEFAULT_SPLITTER_STATE,
    DEFAULT_WINDOW_HEIGHT,
    DEFAULT_WINDOW_WIDTH,
    get_splitter_state,
    set_splitter_state,
    set_bands_splitter_state,
    set_setlists_splitter_state,
    set_setlists_editor_splitter_state,
)


def _coerce_saved_maximized(value) -> bool:
    """JSON may only guarantee booleans; tolerate legacy hand-edited values without bool('false') == True."""
    if value is True:
        return True
    if value is False or value is None:
        return False
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes")
    if isinstance(value, (int, float)):
        return value != 0
    return False


def _clip_rect_to_screens(rect: QRect) -> QRect:
    """If the saved position is off every display (e.g. unplugged monitor), center on primary."""
    if QGuiApplication.screenAt(rect.center()) is not None:
        return rect
    primary = QGuiApplication.primaryScreen()
    if primary is None:
        return rect
    ag = primary.availableGeometry()
    x = ag.x() + max(0, (ag.width() - rect.width()) // 2)
    y = ag.y() + max(0, (ag.height() - rect.height()) // 2)
    return QRect(x, y, rect.width(), rect.height())


WINDOW_GEOMETRY_PREFS_VERSION = 2


def _restore_window_geometry(window: QMainWindow) -> None:
    """Restore main window size and position from preferences if available."""
    saved = preferences.get_window_geometry()
    if not saved:
        return
    if isinstance(saved, dict) and saved.get("v") == WINDOW_GEOMETRY_PREFS_VERSION:
        qt = saved.get("qt")
        if isinstance(qt, str) and qt.strip():
            data = QByteArray.fromBase64(qt.strip().encode("ascii"))
            if not data.isEmpty():
                # Defer to first showEvent: on Windows, restoreGeometry needs a shown top-level
                # to apply the correct monitor + maximized state.
                window._pending_restore_geometry = data
        return
    if isinstance(saved, dict):
        # Legacy v1 human-readable format: {x, y, width, height, maximized}
        try:
            x = int(saved.get("x", 0))
            y = int(saved.get("y", 0))
            w = int(saved.get("width", DEFAULT_WINDOW_WIDTH))
            h = int(saved.get("height", DEFAULT_WINDOW_HEIGHT))
        except (TypeError, ValueError):
            x, y = 0, 0
            w, h = DEFAULT_WINDOW_WIDTH, DEFAULT_WINDOW_HEIGHT
        want_max = _coerce_saved_maximized(saved.get("maximized"))
        w = max(w, window.minimumWidth())
        h = max(h, window.minimumHeight())
        rect = _clip_rect_to_screens(QRect(x, y, w, h))
        window.setWindowState(Qt.WindowState.WindowNoState)
        window.setGeometry(rect)
        if want_max:

            def _maximize() -> None:
                window.setWindowState(window.windowState() | Qt.WindowState.WindowMaximized)

            QTimer.singleShot(0, _maximize)
        return
    # Legacy: preferences stored raw base64 saveGeometry as a string
    if isinstance(saved, str) and saved.strip():
        data = QByteArray.fromBase64(saved.strip().encode("ascii"))
        if not data.isEmpty():
            window._pending_restore_geometry = data


def _save_window_geometry(window: QMainWindow) -> None:
    """Persist QWidget.saveGeometry() (placement, screen, and maximized state) for multi-monitor Win32."""
    qba = window.saveGeometry()
    if qba.isEmpty():
        return
    b64 = base64.b64encode(qba.data()).decode("ascii")
    preferences.set_window_geometry({"v": WINDOW_GEOMETRY_PREFS_VERSION, "qt": b64})


class PlaceholderPage(QWidget):
    """Placeholder content for a section."""

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(title))
        layout.addStretch()


class MainWindow(QMainWindow):
    """Main application window with navigation and stacked content."""

    # Set Playback temporarily disabled (half-baked, not functional yet)
    PAGES = ["Library", "Setlists", "Bands", "Settings"]

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
        self._pending_restore_geometry: QByteArray | None = None
        self.setMinimumSize(900, 600)
        if not preferences.get_window_geometry():
            self.resize(DEFAULT_WINDOW_WIDTH, DEFAULT_WINDOW_HEIGHT)
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
        # from .set_playback_view import SetPlaybackView  # disabled
        from .settings_view import SettingsView
        self.library_view = LibraryView(app_state, self.playback_state)
        self.setlists_view = SetlistsView(app_state, self.playback_state)
        self.bands_view = BandsView(app_state)
        self.stacked.addWidget(self.library_view)
        self.stacked.addWidget(self.setlists_view)
        self.stacked.addWidget(self.bands_view)
        # self.stacked.addWidget(SetPlaybackView(app_state, self.playback_state))  # disabled
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
        pending = getattr(self, "_pending_restore_geometry", None)
        if pending is not None:
            self._pending_restore_geometry = None
            self.restoreGeometry(pending)
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
            left_default, right_default = DEFAULT_SPLITTER_STATE[0], DEFAULT_SPLITTER_STATE[1]
            total_default = left_default + right_default
            ratio = left_default / total_default if total_default > 0 else 0.08
            nav_w = int(total * ratio)
            nav_w = max(self.nav_list.minimumWidth(), min(self.nav_list.maximumWidth(), nav_w))
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
        file_menu.addAction("Analyze &duplicate folders…", self._on_analyze_duplicate_folders)
        file_menu.addAction("&Settings", self._on_settings)
        file_menu.addAction("Write &PluginData...", self._on_write_plugindata)
        file_menu.addSeparator()
        file_menu.addAction("E&xit", QApplication.quit)
        view_menu = menubar.addMenu("&View")
        for i, name in enumerate(self.PAGES):
            view_menu.addAction(name, lambda checked=False, idx=i: self._go_to_page(idx))
        help_menu = menubar.addMenu("&Help")
        help_menu.addAction("&User Guide", self._on_user_guide)
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
        from .duplicate_batch_dialog import show_batch_duplicate_review

        def on_duplicates_batch(conn, pending):
            return show_batch_duplicate_review(conn, pending)

        def on_folder_review(conn, folder_clusters, pending):
            reply = QMessageBox.question(
                self,
                "Duplicate folders",
                f"Found {len(folder_clusters)} duplicate folder structure(s). "
                "Review them before resolving file-level duplicates?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return set()
            from .folder_duplicate_dialog import show_folder_duplicate_dialog_for_scan
            return show_folder_duplicate_dialog_for_scan(self, conn, folder_clusters, len(pending))

        self.statusBar().showMessage("Scanning...")
        QApplication.processEvents()
        try:
            total, scanned, errors = run_scan(
                self.app_state.conn,
                progress_callback=lambda i, n: self.statusBar().showMessage(f"Scanning {i}/{n}..."),
                on_duplicates_batch=on_duplicates_batch,
                on_folder_duplicates_review=on_folder_review,
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

    def _on_analyze_duplicate_folders(self) -> None:
        from ..db.folder_rule import get_enabled_roots
        from ..scanning.folder_duplicate_detect import detect_duplicate_folder_clusters
        from ..scanning.scanner import _normalize_path
        from .folder_duplicate_dialog import show_standalone_folder_duplicate_dialog

        conn = self.app_state.conn
        lib, set_r, excl = get_enabled_roots(conn)
        lib_n = [_normalize_path(p) for p in lib]
        set_n = [_normalize_path(p) for p in set_r]
        excl_n = [_normalize_path(p) for p in excl]
        if not lib_n:
            QMessageBox.information(self, "Duplicate folders", "No library root configured.")
            return
        self.statusBar().showMessage("Analyzing folders…")
        QApplication.processEvents()
        try:
            clusters = detect_duplicate_folder_clusters(lib_n, set_n, excl_n)
        except Exception as e:
            QMessageBox.critical(self, "Duplicate folders", str(e))
            return
        finally:
            self.statusBar().clearMessage()
        if not clusters:
            QMessageBox.information(self, "Duplicate folders", "No duplicate folder structures found.")
            return
        show_standalone_folder_duplicate_dialog(self, conn, clusters)
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

    def _on_user_guide(self) -> None:
        from .readme_viewer_dialog import open_readme_viewer
        open_readme_viewer(self)

    def _on_about(self) -> None:
        from ..version import __version__
        msg = (
            f"ABC Music Manager — Version {__version__}\n\n"
            "Local-first desktop app for ABC music library and setlist management.\n\n"
            "Copyright (c) 2026 Willow Aevoreth Rowan\n"
            "Licensed under the MIT License. See LICENSE.txt.\n\n"
            "Third-party components:\n"
            "• Qt / PySide6 — LGPL-3.0 (The Qt Company Ltd.)\n"
            "• Maestro — ABC-to-MIDI, instrument mappings (digero, NikolaiVChr); MIT\n"
            "• LotroInstruments.sf2 — Optional soundfont (NikolaiVChr/mver)\n"
            "• superqt, Send2Trash, tinysoundfont, PyAudio, mido — permissive licenses\n\n"
            "See NOTICE.txt for full license and attribution details."
        )
        QMessageBox.about(self, "About ABC Music Manager", msg)
