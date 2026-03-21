"""
Playback toolbar: prev/play/stop/next, volume, tempo, parts+playlist dropdown,
elapsed/total meter, scrub, stereo effect, stereo format.
"""

from __future__ import annotations

import math as _math
import time
from typing import TYPE_CHECKING

from PySide6.QtWidgets import (
    QToolBar,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QSlider,
    QLabel,
    QFrame,
    QScrollArea,
    QCheckBox,
    QComboBox,
    QInputDialog,
    QMessageBox,
    QSizePolicy,
    QStyle,
    QStyleOptionSlider,
    QApplication,
    QAbstractItemView,
    QMenu,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QSplitter,
    QSizeGrip,
)
from PySide6.QtCore import Qt, Signal, QTimer, QPoint, QObject, QEvent, QRect, QMimeData
from PySide6.QtGui import QMouseEvent, QDrag

from ..services.playback_state import PlaybackState, PlaylistEntry
from ..services import preferences

if TYPE_CHECKING:
    from ..services.app_state import AppState


class _PopupCloseFilter(QObject):
    """When popup hides (e.g. click outside), uncheck the dropdown button."""

    def __init__(self, popup: QWidget, on_hidden, btn: QPushButton, parent=None):
        super().__init__(parent)
        self._popup = popup
        self._on_hidden = on_hidden
        self._btn = btn

    def eventFilter(self, obj, event):
        if obj == self._popup and event.type() == QEvent.Type.Hide:
            self._on_hidden()
        return False


def _icon_char(c: str) -> str:
    """Use Unicode symbols as fallback when no icon theme."""
    return c


# Tempo: 0.5-2.0, 1.0 at center (snapping point). Log scale so center = 1x
_TEMPO_MIN = 0.5
_TEMPO_MAX = 2.0
_TEMPO_SNAP = 1.0
_TEMPO_LOG_MIN = _math.log(_TEMPO_MIN)
_TEMPO_LOG_MAX = _math.log(_TEMPO_MAX)


def _tempo_slider_to_value(slider_val: int) -> float:
    t = slider_val / 400.0
    log_val = _TEMPO_LOG_MIN + t * (_TEMPO_LOG_MAX - _TEMPO_LOG_MIN)
    v = _math.exp(log_val)
    if abs(v - _TEMPO_SNAP) < 0.08:
        return _TEMPO_SNAP
    return round(v * 20) / 20


def _tempo_value_to_slider(val: float) -> int:
    log_val = _math.log(max(_TEMPO_MIN, min(_TEMPO_MAX, val)))
    t = (log_val - _TEMPO_LOG_MIN) / (_TEMPO_LOG_MAX - _TEMPO_LOG_MIN)
    return int(400 * t)


class TempoButtonWithPopup(QPushButton):
    """Button showing current tempo; click opens vertical slider under button. Second click closes."""

    def __init__(self, playback_state: PlaybackState, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._state = playback_state
        self._popup: QWidget | None = None
        self._slider: QSlider | None = None
        self._update_text()
        self.setToolTip("Tempo (click for slider: 0.5×–2×)")
        self.clicked.connect(self._on_clicked)

    def _update_text(self) -> None:
        self.setText(f"{self._state.tempo_factor:.2f}×")

    def _on_clicked(self) -> None:
        if self._popup and self._popup.isVisible():
            self._popup.hide()  # Event filter applies tempo on hide
            return
        self._show_popup()

    def _show_popup(self) -> None:
        popup = QFrame()
        popup.setFrameShape(QFrame.Shape.StyledPanel)
        popup.setWindowFlags(
            Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
        )
        layout = QVBoxLayout(popup)
        layout.setContentsMargins(12, 12, 12, 12)
        lbl = QLabel("1×")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(lbl)
        slider = QSlider(Qt.Orientation.Vertical)
        slider.setRange(0, 400)
        slider.setValue(_tempo_value_to_slider(self._state.tempo_factor))
        slider.setFixedHeight(120)
        slider.setInvertedAppearance(True)

        def update_label(val: int) -> None:
            v = _tempo_slider_to_value(val)
            lbl.setText(f"{v:.2f}×")

        def on_released() -> None:
            v = _tempo_slider_to_value(slider.value())
            self._state.tempo_factor = v
            self._update_text()

        slider.valueChanged.connect(update_label)
        slider.sliderReleased.connect(on_released)
        update_label(slider.value())
        layout.addWidget(slider)

        self._popup = popup
        self._slider = slider

        def apply_tempo_on_close() -> None:
            if self._slider is not None:
                v = _tempo_slider_to_value(self._slider.value())
                if abs(v - self._state.tempo_factor) >= 1e-6:
                    self._state.tempo_factor = v
                self._update_text()

        close_filter = _PopupCloseFilter(popup, apply_tempo_on_close, self, self)
        popup.installEventFilter(close_filter)

        # Explicit size so popup is never zero-sized
        popup.setMinimumSize(80, 160)
        popup.adjustSize()
        # Position upper-left just under button's bottom-left
        QApplication.processEvents()
        btn_bottom_left = self.mapToGlobal(self.rect().bottomLeft())
        popup.move(btn_bottom_left.x(), btn_bottom_left.y() + 4)
        # Ensure popup fits on the screen that contains the button
        screen = self.screen() or QApplication.primaryScreen()
        if screen:
            gr = screen.availableGeometry()
            x, y = popup.x(), popup.y()
            if y + popup.height() > gr.bottom():
                y = max(gr.top(), gr.bottom() - popup.height() - 20)
            if x + popup.width() > gr.right():
                x = max(gr.left(), gr.right() - popup.width() - 20)
            if x < gr.left():
                x = gr.left() + 20
            popup.move(x, y)
        popup.show()
        popup.raise_()
        popup.activateWindow()


_MIME_PLAYLIST_ROW = "application/x-playback-playlist-row"


def _fmt_duration(sec: float | None) -> str:
    if sec is None or sec < 0:
        return "—"
    m = int(sec // 60)
    s = int(sec % 60)
    return f"{m}:{s:02d}" if m > 0 else f"0:{s:02d}"


class PlaylistTable(QTableWidget):
    """Table with drag-drop row reorder, like setlist songs table."""

    rowReordered = None  # Set by parent: callable() -> None

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        self.setDragDropOverwriteMode(False)
        self.setDefaultDropAction(Qt.DropAction.CopyAction)
        self.setDropIndicatorShown(True)
        self._drag_row: int = -1

    def startDrag(self, supportedActions) -> None:
        row = self.currentRow()
        if row < 0:
            return
        self._drag_row = row
        mime = QMimeData()
        mime.setData(_MIME_PLAYLIST_ROW, str(row).encode("utf-8"))
        indexes = [self.model().index(row, c) for c in range(self.model().columnCount())]
        model_mime = self.model().mimeData(indexes)
        if model_mime:
            model_mime.setData(_MIME_PLAYLIST_ROW, str(row).encode("utf-8"))
            mime = model_mime
        drag = QDrag(self)
        drag.setMimeData(mime)
        # Use CopyAction so Qt does not remove source rows; we move them ourselves in dragMoveEvent.
        drag.exec(Qt.DropAction.CopyAction)
        self._drag_row = -1

    def _move_row_visually(self, from_row: int, to_row: int) -> None:
        if from_row == to_row or from_row < 0 or to_row < 0:
            return
        n = self.rowCount()
        if from_row >= n or to_row > n:
            return
        items = [self.takeItem(from_row, c) for c in range(self.columnCount())]
        self.removeRow(from_row)
        if to_row > from_row:
            to_row -= 1
        self.insertRow(to_row)
        for c, it in enumerate(items):
            self.setItem(to_row, c, it)
        self._drag_row = to_row
        self.selectRow(to_row)

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasFormat(_MIME_PLAYLIST_ROW):
            event.acceptProposedAction()
            super().dragEnterEvent(event)
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:
        if not event.mimeData().hasFormat(_MIME_PLAYLIST_ROW) or self._drag_row < 0:
            event.ignore()
            return
        event.acceptProposedAction()
        pos = event.position().toPoint()
        idx = self.indexAt(pos)
        row = idx.row()
        if row >= 0:
            rect = self.visualRect(idx)
            if pos.y() > rect.center().y():
                drop_row = row + 1
            else:
                drop_row = row
        else:
            drop_row = self.rowCount()
        if drop_row != self._drag_row:
            self._move_row_visually(self._drag_row, drop_row)
        super().dragMoveEvent(event)

    def dropEvent(self, event) -> None:
        mime = event.mimeData()
        if not mime.hasFormat(_MIME_PLAYLIST_ROW):
            event.ignore()
            return
        event.acceptProposedAction()
        event.setDropAction(Qt.DropAction.CopyAction)
        # Apply reorder synchronously while table state is correct.
        if self.rowReordered:
            self.rowReordered()


class ClickableScrubSlider(QSlider):
    """
    Scrub slider that supports both click-to-jump and drag-to-scrub.
    Click anywhere on the track to seek; click-and-drag to scrub through the song.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(Qt.Orientation.Horizontal, parent)
        self._scrub_dragging = False

    def _value_from_pos(self, pos: QPoint) -> int:
        opt = QStyleOptionSlider()
        self.initStyleOption(opt)
        groove = self.style().subControlRect(
            QStyle.ComplexControl.CC_Slider, opt, QStyle.SubControl.SC_SliderGroove, self
        )
        span = max(1, groove.width() - 1 if self.orientation() == Qt.Orientation.Horizontal else groove.height() - 1)
        pos_in_span = pos.x() - groove.x() if self.orientation() == Qt.Orientation.Horizontal else pos.y() - groove.y()
        pos_in_span = max(0, min(span, pos_in_span))
        return QStyle.sliderValueFromPosition(
            self.minimum(), self.maximum(), pos_in_span, span, opt.upsideDown
        )

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            opt = QStyleOptionSlider()
            self.initStyleOption(opt)
            groove = self.style().subControlRect(
                QStyle.ComplexControl.CC_Slider, opt, QStyle.SubControl.SC_SliderGroove, self
            )
            handle = self.style().subControlRect(
                QStyle.ComplexControl.CC_Slider, opt, QStyle.SubControl.SC_SliderHandle, self
            )
            pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
            if not handle.contains(pos) and groove.contains(pos):
                # Click on groove: jump and start drag so user can scrub by dragging
                value = self._value_from_pos(pos)
                self.setValue(value)
                self._scrub_dragging = True
                self.grabMouse()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._scrub_dragging:
            pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
            self.setValue(self._value_from_pos(pos))
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._scrub_dragging:
            self._scrub_dragging = False
            self.releaseMouse()
            pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
            self.setValue(self._value_from_pos(pos))
            return
        super().mouseReleaseEvent(event)


class PlaybackToolbar(QToolBar):
    """
    Persistent playback toolbar.
    Order: Prev | Play | Stop | Next | Vol | Tempo | Dropdown (parts+playlist) | Meter | Scrub | Stereo slider | Stereo format
    """

    playlistExportedAsSet = Signal(int)  # setlist_id

    def __init__(
        self,
        playback_state: PlaybackState,
        parent: QWidget | None = None,
        *,
        app_state: "AppState | None" = None,
    ) -> None:
        super().__init__(parent)
        self._state = playback_state
        self._app_state = app_state
        self._last_prev_click_time = 0.0
        self.setObjectName("playback_toolbar")
        self.setMovable(False)
        self.setFloatable(False)

        self._prev_btn = QPushButton(_icon_char("⏮"))
        self._prev_btn.setToolTip("Previous (rewind to start; click again within 1s for prev song)")
        self._prev_btn.clicked.connect(self._on_prev)

        self._play_btn = QPushButton(_icon_char("▶") + " Play")
        self._play_btn.setToolTip("Play")
        self._play_btn.setFixedWidth(
            self._play_btn.fontMetrics().horizontalAdvance(_icon_char("▶") + " Resume") + 24
        )
        self._play_btn.clicked.connect(self._on_play)

        self._stop_btn = QPushButton(_icon_char("■") + " Stop")
        self._stop_btn.setToolTip("Stop (double-click for MIDI panic)")
        self._stop_btn.clicked.connect(self._on_stop_clicked)
        self._stop_single_click_timer: QTimer | None = None

        self._next_btn = QPushButton(_icon_char("⏭"))
        self._next_btn.setToolTip("Next track")
        self._next_btn.clicked.connect(self._on_next)

        self.addWidget(self._prev_btn)
        self.addWidget(self._play_btn)
        self.addWidget(self._stop_btn)
        self.addWidget(self._next_btn)
        self.addSeparator()

        self._vol_slider = QSlider(Qt.Orientation.Horizontal)
        self._vol_slider.setRange(0, 100)
        self._vol_slider.setValue(int(playback_state.volume))
        self._vol_slider.setMaximumWidth(80)
        self._vol_slider.setToolTip("Volume")
        self._vol_slider.valueChanged.connect(self._on_volume_changed)
        self.addWidget(QLabel("Vol"))
        self.addWidget(self._vol_slider)
        self.addSeparator()

        self._tempo_btn = TempoButtonWithPopup(playback_state)
        self.addWidget(self._tempo_btn)
        self.addSeparator()

        self._dropdown_btn = QPushButton(_icon_char("▼") + " Parts & Playlist")
        self._dropdown_btn.setToolTip("Instruments (mute) & Playlist (reorder, remove)")
        self._dropdown_btn.setCheckable(True)
        self._dropdown_btn.toggled.connect(self._on_dropdown_toggled)
        self.addWidget(self._dropdown_btn)
        self.addSeparator()

        self._pos_label = QLabel("0:00 / 0:00")
        self._pos_label.setMinimumWidth(80)
        self._scrub_slider = ClickableScrubSlider()
        self._scrub_slider.setRange(0, 1000)
        self._scrub_slider.setValue(0)
        self._scrub_slider.setToolTip("Position (click or drag to seek)")
        self._scrub_slider.valueChanged.connect(self._on_scrub_moved)
        self.addWidget(self._pos_label)
        self.addWidget(self._scrub_slider)
        self.addSeparator()

        self._stereo_slider = QSlider(Qt.Orientation.Horizontal)
        self._stereo_slider.setRange(0, 100)
        self._stereo_slider.setValue(playback_state.stereo_slider)
        self._stereo_slider.setMaximumWidth(80)
        self._stereo_slider.setToolTip("Distance from band (0=close L/R, 100=equal)")
        self._stereo_slider.valueChanged.connect(self._on_stereo_slider_changed)
        self.addWidget(QLabel("Stereo"))
        self.addWidget(self._stereo_slider)
        self.addSeparator()

        self._stereo_combo = QComboBox()
        self._stereo_combo.addItem("Band layout", "band_layout")
        self._stereo_combo.addItem("Maestro: user-pan", "maestro_user_pan")
        self._stereo_combo.addItem("Maestro: Default", "maestro")
        idx = self._stereo_combo.findData(playback_state.stereo_mode)
        self._stereo_combo.setCurrentIndex(max(0, idx))
        self._stereo_combo.setToolTip(
            "Pan method: Band layout = position; user-pan = %%user-pan from file; Default = instrument-based"
        )
        self._stereo_combo.currentIndexChanged.connect(self._on_stereo_changed)
        self.addWidget(self._stereo_combo)

        self._dropdown_panel: QWidget | None = None
        self._dropdown_popup: QWidget | None = None

        playback_state.position_changed.connect(self._on_position_changed)
        playback_state.state_changed.connect(self._update_ui)

        self._install_stop_double_click()

    def _install_stop_double_click(self) -> None:
        """Install filter so double-click = panic, single-click = stop.
        Uses timer to avoid both firing: single-click defers stop; double-click cancels timer and panics."""
        from PySide6.QtCore import QObject, QEvent

        class DoubleClickFilter(QObject):
            def __init__(self, on_double, parent=None):
                super().__init__(parent)
                self._on_double = on_double

            def eventFilter(self, obj, event):
                if event.type() == QEvent.Type.MouseButtonDblClick:
                    self._on_double()
                    return True
                return False

        self._stop_dbl_filter = DoubleClickFilter(self._on_stop_double_clicked, self)
        self._stop_btn.installEventFilter(self._stop_dbl_filter)

    def _cancel_stop_single_click_timer(self) -> None:
        if self._stop_single_click_timer is not None:
            self._stop_single_click_timer.stop()
            self._stop_single_click_timer.deleteLater()
            self._stop_single_click_timer = None

    def _build_dropdown_panel(self) -> None:
        """Build dropdown: two columns - Parts (mute) | Playlist table. Resizable, geometry saved."""
        self._parts_playlist_splitter = QSplitter(Qt.Orientation.Horizontal)
        self._parts_playlist_save_timer = QTimer(self)
        self._parts_playlist_save_timer.setSingleShot(True)
        self._parts_playlist_save_timer.timeout.connect(self._save_parts_playlist_state)

        # Left: Parts
        parts_w = QWidget()
        parts_layout = QVBoxLayout(parts_w)
        parts_layout.addWidget(QLabel("Parts"))
        self._parts_container = QWidget()
        self._parts_inner = QVBoxLayout(self._parts_container)
        self._parts_inner.addWidget(QLabel("(No song loaded)"))
        parts_scroll = QScrollArea()
        parts_scroll.setWidget(self._parts_container)
        parts_scroll.setWidgetResizable(True)
        parts_scroll.setMinimumWidth(120)
        parts_scroll.setMinimumHeight(360)
        parts_layout.addWidget(parts_scroll)
        self._parts_playlist_splitter.addWidget(parts_w)

        # Right: Playlist table (play indicator | Title | Parts | Duration | Composer)
        playlist_layout = QVBoxLayout()
        playlist_layout.addWidget(QLabel("Playlist"))
        self._playlist_table = PlaylistTable()
        self._playlist_table.setColumnCount(5)
        self._playlist_table.setHorizontalHeaderLabels(["", "Title", "Parts", "Duration", "Composer"])
        hh = self._playlist_table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self._playlist_table.setColumnWidth(0, 28)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for c in range(2, 5):
            hh.setSectionResizeMode(c, QHeaderView.ResizeMode.Interactive)
        self._playlist_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._playlist_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._playlist_table.setMinimumHeight(200)
        self._playlist_table.rowReordered = self._on_playlist_reordered
        self._playlist_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._playlist_table.customContextMenuRequested.connect(self._on_playlist_context_menu)
        self._playlist_table.cellDoubleClicked.connect(self._on_playlist_cell_double_clicked)
        self._playlist_table.horizontalHeader().sectionResized.connect(self._on_playlist_header_resized)
        playlist_w = QWidget()
        pl_layout = QVBoxLayout(playlist_w)
        self._export_playlist_btn = QPushButton("Export playlist as set")
        self._export_playlist_btn.setToolTip("Create a new setlist from the current playlist order")
        self._export_playlist_btn.clicked.connect(self._on_export_playlist_as_set)
        pl_layout.addWidget(self._export_playlist_btn)
        pl_layout.addWidget(self._playlist_table)
        self._parts_playlist_splitter.addWidget(playlist_w)

        self._parts_playlist_splitter.setStretchFactor(0, 0)
        self._parts_playlist_splitter.setStretchFactor(1, 1)
        saved_split = preferences.get_parts_playlist_splitter_state()
        if saved_split and len(saved_split) >= 2:
            self._parts_playlist_splitter.setSizes(saved_split)
        else:
            self._parts_playlist_splitter.setSizes([160, 400])
        self._parts_playlist_splitter.splitterMoved.connect(self._on_parts_playlist_splitter_moved)

        panel = QFrame()
        panel.setFrameStyle(QFrame.Shape.StyledPanel)
        panel_layout = QVBoxLayout(panel)
        panel_layout.addWidget(self._parts_playlist_splitter)

        scroll = QScrollArea()
        scroll.setWidget(panel)
        scroll.setWidgetResizable(True)
        scroll.setMinimumSize(500, 350)
        self._dropdown_panel = scroll
        popup = QWidget(self.window())
        popup.setWindowFlags(
            Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
        )
        popup_layout = QVBoxLayout(popup)
        popup_layout.setContentsMargins(2, 2, 2, 2)
        popup_layout.addWidget(scroll)
        grip_row = QHBoxLayout()
        grip_row.addStretch()
        grip_row.addWidget(QSizeGrip(popup))
        popup_layout.addLayout(grip_row)
        popup.setMinimumSize(504, 354)
        geom = preferences.get_parts_playlist_popup_geometry()
        if geom:
            popup.resize(geom["width"], geom["height"])
        else:
            popup.resize(600, 440)

        def on_popup_hidden() -> None:
            self._save_parts_playlist_state()
            self._dropdown_btn.blockSignals(True)
            self._dropdown_btn.setChecked(False)
            self._dropdown_btn.blockSignals(False)

        popup.installEventFilter(_PopupCloseFilter(popup, on_popup_hidden, self._dropdown_btn, self))
        self._state.playlist_changed.connect(self._refresh_dropdown)
        self._state.state_changed.connect(self._refresh_dropdown)
        self._refresh_dropdown()

        self._dropdown_popup = popup

    def _save_parts_playlist_state(self) -> None:
        """Save popup geometry, splitter sizes, table column widths to preferences."""
        if self._dropdown_popup:
            w, h = self._dropdown_popup.width(), self._dropdown_popup.height()
            if w >= 400 and h >= 300:
                preferences.set_parts_playlist_popup_geometry(w, h)
        if hasattr(self, "_parts_playlist_splitter") and self._parts_playlist_splitter:
            preferences.set_parts_playlist_splitter_state(self._parts_playlist_splitter.sizes())
        if hasattr(self, "_playlist_table") and self._playlist_table.columnCount() >= 5:
            w = [self._playlist_table.columnWidth(c) for c in range(5)]
            preferences.set_playback_playlist_table_columns(w)

    def _on_parts_playlist_splitter_moved(self) -> None:
        self._parts_playlist_save_timer.start(200)

    def _on_playlist_header_resized(self) -> None:
        if hasattr(self, "_parts_playlist_save_timer") and self._parts_playlist_save_timer:
            self._parts_playlist_save_timer.start(200)

    def _refresh_dropdown(self) -> None:
        self._refresh_parts_display()
        self._refresh_playlist_list()
        if hasattr(self, "_export_playlist_btn"):
            self._export_playlist_btn.setEnabled(bool(self._state.playlist))

    def _refresh_parts_display(self) -> None:
        if not hasattr(self, "_parts_inner"):
            return
        layout = self._parts_inner
        while layout.count() > 0:
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        song_id = self._state.current_song_id
        if not self._app_state or not song_id:
            layout.addWidget(QLabel("(No song loaded)"))
            layout.addStretch()
            return
        try:
            from ..db.library_query import get_song_for_detail
            detail = get_song_for_detail(self._app_state.conn, song_id)
        except Exception:
            layout.addWidget(QLabel("(No song loaded)"))
            layout.addStretch()
            return
        if not detail or not detail.get("parts"):
            layout.addWidget(QLabel("(No parts)"))
            layout.addStretch()
            return
        mutes = self._state.part_mutes
        for idx, p in enumerate(detail["parts"]):
            if idx >= 24:
                break  # MIDI supports up to 24 parts (LOTRO limit)
            pnum = int(p.get("part_number", 0))
            name = p.get("part_name") or p.get("instrument_name") or f"Part {pnum}"
            cb = QCheckBox(name)
            cb.blockSignals(True)
            cb.setChecked(not mutes.get(idx, False))
            cb.blockSignals(False)

            def make_handler(channel_idx: int):
                def handler(checked: int) -> None:
                    self._state.set_part_muted(channel_idx, checked != Qt.CheckState.Checked.value)
                return handler

            cb.stateChanged.connect(make_handler(idx))
            layout.addWidget(cb)
        layout.addStretch()

    def _refresh_playlist_list(self) -> None:
        if not hasattr(self, "_playlist_table"):
            return
        self._playlist_table.blockSignals(True)
        self._playlist_table.setRowCount(0)
        if not self._app_state:
            self._playlist_table.blockSignals(False)
            return
        try:
            from ..db.library_query import get_song_for_detail, get_song_id_for_file_path
            current_idx = self._state.current_index
            playing_or_paused = self._state.is_playing or self._state.is_paused
            for i, entry in enumerate(self._state.playlist):
                sid = entry.song_id or get_song_id_for_file_path(self._app_state.conn, entry.file_path)
                detail = get_song_for_detail(self._app_state.conn, sid) if sid else None
                part_count = detail.get("part_count", 0) if detail else 0
                duration_sec = detail.get("duration_seconds") if detail else None
                composers = (detail.get("composers") or "—") if detail else "—"
                self._playlist_table.insertRow(i)
                # Col 0: play indicator
                play_item = QTableWidgetItem("▶" if i == current_idx and playing_or_paused else "")
                play_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                play_item.setFlags(play_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self._playlist_table.setItem(i, 0, play_item)
                # Col 1: title (UserRole: original index for reorder mapping)
                t = QTableWidgetItem(entry.title)
                t.setData(Qt.ItemDataRole.UserRole, (sid, i) if sid else i)
                t.setFlags(t.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self._playlist_table.setItem(i, 1, t)
                # Cols 2-4
                for col, val in enumerate((str(part_count), _fmt_duration(duration_sec), composers), 2):
                    it = QTableWidgetItem(val)
                    it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    self._playlist_table.setItem(i, col, it)
            # Restore column widths from preferences (first refresh only, when we have rows)
            if self._playlist_table.rowCount() > 0 and not getattr(self, "_playlist_columns_restored", False):
                self._playlist_columns_restored = True
                saved = preferences.get_playback_playlist_table_columns()
                if saved and len(saved) >= 5:
                    for c, w in enumerate(saved[:5]):
                        self._playlist_table.setColumnWidth(c, max(28 if c == 0 else 40, w))
        except Exception:
            pass
        self._playlist_table.blockSignals(False)

    def _on_playlist_reordered(self) -> None:
        if not hasattr(self, "_playlist_table"):
            return
        indices = []
        for row in range(self._playlist_table.rowCount()):
            it = self._playlist_table.item(row, 1)
            if it:
                val = it.data(Qt.ItemDataRole.UserRole)
                if isinstance(val, tuple):
                    indices.append(val[1])
                elif val is not None:
                    indices.append(val)
                else:
                    indices.append(row)
        if len(indices) == len(self._state.playlist):
            self._state.reorder_playlist(indices)

    def _on_playlist_cell_double_clicked(self, row: int, col: int) -> None:
        """Double-click on song in queue: jump to that song and start playing."""
        if 0 <= row < len(self._state.playlist):
            self._state.go_to_index(row)

    def _on_export_playlist_as_set(self) -> None:
        """Create a new setlist from the current playlist and switch to Setlists view."""
        if not self._app_state or not self._state.playlist:
            QMessageBox.information(
                self,
                "Export playlist as set",
                "Playlist is empty. Add songs first.",
            )
            return
        # Hide dropdown first: it has WindowStaysOnTopHint so dialogs would appear behind it
        if hasattr(self, "_dropdown_popup") and self._dropdown_popup and self._dropdown_popup.isVisible():
            self._dropdown_popup.hide()
        from ..db.library_query import get_song_id_for_file_path
        from ..db.setlist_repo import add_setlist, add_setlist_item

        name, ok = QInputDialog.getText(
            self,
            "Export playlist as set",
            "Setlist name:",
            text=f"Playlist {len(self._state.playlist)} songs",
        )
        if not ok or not name.strip():
            return
        song_ids: list[int] = []
        for entry in self._state.playlist:
            sid = entry.song_id or (
                get_song_id_for_file_path(self._app_state.conn, entry.file_path) if entry.file_path else None
            )
            if sid:
                song_ids.append(sid)

        if not song_ids:
            QMessageBox.warning(
                self,
                "Export playlist as set",
                "No playlist songs found in library. Scan your library first.",
            )
            return
        setlist_id = add_setlist(self._app_state.conn, name.strip())
        for pos, song_id in enumerate(song_ids):
            add_setlist_item(self._app_state.conn, setlist_id, song_id, position=pos)
        skipped = len(self._state.playlist) - len(song_ids)
        self.playlistExportedAsSet.emit(setlist_id)
        msg = f"Created setlist '{name.strip()}' with {len(song_ids)} song(s)."
        if skipped:
            msg += f" ({skipped} not in library, skipped.)"
        QMessageBox.information(self, "Export playlist as set", msg)

    def _on_playlist_context_menu(self, pos: QPoint) -> None:
        if not hasattr(self, "_playlist_table"):
            return
        idx = self._playlist_table.indexAt(pos)
        row = idx.row()
        if row < 0 or row >= len(self._state.playlist):
            return
        menu = QMenu(self)
        menu.addAction("Remove from queue", lambda r=row: self._state.remove_from_playlist(r))
        menu.exec(self._playlist_table.mapToGlobal(pos))

    def _on_prev(self) -> None:
        now = time.monotonic()
        seconds_since = now - self._last_prev_click_time
        self._state.previous_track_or_rewind(seconds_since)
        self._last_prev_click_time = now

    def _on_play(self) -> None:
        if self._state.is_playing:
            self._state.pause()
        else:
            self._state.play()

    def _on_next(self) -> None:
        self._state.next_track()

    def _on_stop_clicked(self) -> None:
        """Single-click: defer stop so double-click can cancel it and do panic instead."""
        self._cancel_stop_single_click_timer()
        self._stop_single_click_timer = QTimer(self)
        self._stop_single_click_timer.setSingleShot(True)
        self._stop_single_click_timer.timeout.connect(self._on_stop_single_click_timeout)
        self._stop_single_click_timer.start(250)  # ms - within Qt's double-click interval

    def _on_stop_single_click_timeout(self) -> None:
        self._stop_single_click_timer = None
        self._state.stop()

    def _on_stop_double_clicked(self) -> None:
        """Double-click: cancel deferred stop, do panic (which stops + all_sounds_off)."""
        self._cancel_stop_single_click_timer()
        self._state.panic()

    def _on_scrub_moved(self, value: int) -> None:
        pct = value / 1000.0
        pos = pct * self._state.duration_sec
        self._state.seek(pos)

    def _on_volume_changed(self, value: int) -> None:
        self._state.volume = value

    def _on_stereo_slider_changed(self, value: int) -> None:
        self._state.stereo_slider = value

    def _on_stereo_changed(self, index: int) -> None:
        mode = self._stereo_combo.currentData()
        if mode:
            self._state.stereo_mode = mode

    def _on_position_changed(self, position_sec: float) -> None:
        dur = self._state.duration_sec
        if dur > 0:
            self._scrub_slider.blockSignals(True)
            self._scrub_slider.setValue(int(1000 * position_sec / dur))
            self._scrub_slider.blockSignals(False)
        self._pos_label.setText(f"{_format_time(position_sec)} / {_format_time(dur)}")

    def _update_ui(self) -> None:
        playing = self._state.is_playing
        paused = self._state.is_paused
        if playing:
            self._play_btn.setText(_icon_char("⏸") + " Pause")
        elif paused:
            self._play_btn.setText(_icon_char("▶") + " Resume")
        else:
            self._play_btn.setText(_icon_char("▶") + " Play")
        self._vol_slider.blockSignals(True)
        self._vol_slider.setValue(int(self._state.volume))
        self._vol_slider.blockSignals(False)
        self._tempo_btn._update_text()
        self._stereo_slider.blockSignals(True)
        self._stereo_slider.setValue(self._state.stereo_slider)
        self._stereo_slider.blockSignals(False)
        self._stereo_combo.blockSignals(True)
        idx = self._stereo_combo.findData(self._state.stereo_mode)
        self._stereo_combo.setCurrentIndex(max(0, idx))
        self._stereo_combo.blockSignals(False)

    def _on_dropdown_toggled(self, checked: bool) -> None:
        if checked:
            if self._dropdown_panel is None:
                self._build_dropdown_panel()
            if self._dropdown_popup:
                # Restore saved size (adjustSize would reset to content size and forget user resize)
                geom = preferences.get_parts_playlist_popup_geometry()
                if geom:
                    self._dropdown_popup.resize(geom["width"], geom["height"])
                # Position upper-left just under button's bottom-left (same screen as button)
                btn_bottom_left = self._dropdown_btn.mapToGlobal(self._dropdown_btn.rect().bottomLeft())
                self._dropdown_popup.move(btn_bottom_left.x(), btn_bottom_left.y() + 4)
                # Ensure popup fits on the screen that contains the button
                screen = self._dropdown_btn.screen() or QApplication.primaryScreen()
                if screen:
                    gr = screen.availableGeometry()
                    pw, ph = self._dropdown_popup.width(), self._dropdown_popup.height()
                    x, y = self._dropdown_popup.x(), self._dropdown_popup.y()
                    if x + pw > gr.right():
                        x = gr.right() - pw - 20
                    if y + ph > gr.bottom():
                        y = gr.bottom() - ph - 20
                    if x < gr.left():
                        x = gr.left() + 20
                    if y < gr.top():
                        y = gr.top() + 20
                    self._dropdown_popup.move(x, y)
                self._dropdown_popup.show()
                self._dropdown_popup.raise_()
        else:
            if self._dropdown_popup:
                self._dropdown_popup.hide()


def _format_time(sec: float) -> str:
    m = int(sec // 60)
    s = int(sec % 60)
    return f"{m}:{s:02d}"


def _install_stop_double_click(toolbar: PlaybackToolbar) -> None:
    """Install event filter for double-click on stop button."""
    from PySide6.QtCore import QEvent

    class DoubleClickFilter:
        def __init__(self, btn, on_double):
            self.btn = btn
            self.on_double = on_double
            self._last_click = 0.0

        def eventFilter(self, obj, event):
            if obj != self.btn:
                return False
            if event.type() == QEvent.Type.MouseButtonDblClick:
                self.on_double()
                return True
            return False

    from PySide6.QtCore import QObject
    filt = DoubleClickFilter(toolbar._stop_btn, toolbar._on_stop_double_clicked)
    toolbar._stop_btn.installEventFilter(filt)
