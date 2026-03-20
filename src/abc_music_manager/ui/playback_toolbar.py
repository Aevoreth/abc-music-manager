"""
Playback toolbar: play/pause/stop, scrub, volume, tempo, stereo, dropdown toggle.
"""

from __future__ import annotations

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
    QDoubleSpinBox,
    QSizePolicy,
    QMenu,
)
from PySide6.QtCore import Qt, Signal, QTimer, QPoint, QObject, QEvent
from PySide6.QtGui import QAction, QIcon

from ..services.playback_state import PlaybackState, PlaylistEntry


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


class PlaybackToolbar(QToolBar):
    """
    Persistent playback toolbar below menu bar.
    Play, Stop (double-click = panic), scrub, volume, tempo, stereo, dropdown.
    """

    def __init__(self, playback_state: PlaybackState, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._state = playback_state
        self.setObjectName("playback_toolbar")
        self.setMovable(False)
        self.setFloatable(False)

        self._play_btn = QPushButton(_icon_char("▶") + " Play")
        self._play_btn.setToolTip("Play")
        self._play_btn.clicked.connect(self._on_play)

        self._stop_btn = QPushButton(_icon_char("■") + " Stop")
        self._stop_btn.setToolTip("Stop (double-click for MIDI panic)")
        self._stop_btn.clicked.connect(self._on_stop_clicked)
        self._stop_single_click_timer: QTimer | None = None

        self._scrub_slider = QSlider(Qt.Orientation.Horizontal)
        self._scrub_slider.setRange(0, 1000)
        self._scrub_slider.setValue(0)
        self._scrub_slider.setToolTip("Position")
        self._scrub_slider.sliderMoved.connect(self._on_scrub_moved)

        self._pos_label = QLabel("0:00 / 0:00")
        self._pos_label.setMinimumWidth(80)

        self._vol_slider = QSlider(Qt.Orientation.Horizontal)
        self._vol_slider.setRange(0, 100)
        self._vol_slider.setValue(int(playback_state.volume))
        self._vol_slider.setMaximumWidth(80)
        self._vol_slider.setToolTip("Volume")
        self._vol_slider.valueChanged.connect(self._on_volume_changed)

        self._tempo_spin = QDoubleSpinBox()
        self._tempo_spin.setRange(0.5, 2.0)
        self._tempo_spin.setSingleStep(0.1)
        self._tempo_spin.setValue(playback_state.tempo_factor)
        self._tempo_spin.setSuffix("×")
        self._tempo_spin.setToolTip("Tempo")
        self._tempo_spin.setMaximumWidth(70)
        self._tempo_spin.valueChanged.connect(self._on_tempo_changed)

        self._stereo_combo = QComboBox()
        self._stereo_combo.addItems(["Maestro", "Band layout"])
        self._stereo_combo.setCurrentIndex(0 if playback_state.stereo_mode == "maestro" else 1)
        self._stereo_combo.setToolTip("Stereo mode")
        self._stereo_combo.currentIndexChanged.connect(self._on_stereo_changed)

        self._dropdown_btn = QPushButton(_icon_char("▼"))
        self._dropdown_btn.setToolTip("Show parts & playlist")
        self._dropdown_btn.setCheckable(True)
        self._dropdown_btn.toggled.connect(self._on_dropdown_toggled)

        self.addWidget(self._play_btn)
        self.addWidget(self._stop_btn)
        self.addSeparator()
        self.addWidget(self._scrub_slider)
        self.addWidget(self._pos_label)
        self.addSeparator()
        self.addWidget(QLabel("Vol"))
        self.addWidget(self._vol_slider)
        self.addSeparator()
        self.addWidget(QLabel("Tempo"))
        self.addWidget(self._tempo_spin)
        self.addSeparator()
        self.addWidget(QLabel("Stereo"))
        self.addWidget(self._stereo_combo)
        self.addSeparator()
        self.addWidget(self._dropdown_btn)

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
        """Build the dropdown panel (parts mute, playlist, band layout) as popup."""
        panel = QFrame()
        panel.setFrameStyle(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout(panel)
        layout.addWidget(QLabel("Parts"))
        self._parts_container = QWidget()
        parts_layout = QVBoxLayout(self._parts_container)
        parts_layout.addWidget(QLabel("(No song loaded)"))
        layout.addWidget(self._parts_container)
        layout.addWidget(QLabel("Playlist"))
        self._playlist_container = QWidget()
        playlist_layout = QVBoxLayout(self._playlist_container)
        playlist_layout.addWidget(QLabel("(Empty)"))
        layout.addWidget(self._playlist_container)
        scroll = QScrollArea()
        scroll.setWidget(panel)
        scroll.setWidgetResizable(True)
        scroll.setMaximumHeight(200)
        self._dropdown_panel = scroll
        popup = QWidget()
        popup.setWindowFlags(Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        popup_layout = QVBoxLayout(popup)
        popup_layout.setContentsMargins(2, 2, 2, 2)
        popup_layout.addWidget(scroll)
        popup.setFixedWidth(280)
        popup.setFixedHeight(220)
        self._dropdown_popup = popup

        def on_popup_hidden():
            self._dropdown_btn.blockSignals(True)
            self._dropdown_btn.setChecked(False)
            self._dropdown_btn.blockSignals(False)

        popup.installEventFilter(_PopupCloseFilter(popup, on_popup_hidden, self._dropdown_btn, self))
        self._state.playlist_changed.connect(self._refresh_playlist_display)
        self._refresh_playlist_display()

    def _refresh_playlist_display(self) -> None:
        if not hasattr(self, "_playlist_container"):
            return
        # Clear and repopulate
        layout = self._playlist_container.layout()
        if layout:
            while layout.count() > 0:
                item = layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
        if not hasattr(self, "_playlist_container"):
            return
        layout = self._playlist_container.layout()
        if not layout:
            return
        for i, entry in enumerate(self._state.playlist):
            lbl = QLabel(f"{i + 1}. {entry.title}")
            layout.addWidget(lbl)
        if not self._state.playlist:
            layout.addWidget(QLabel("(Empty)"))

    def _on_play(self) -> None:
        if self._state.is_playing:
            return  # TODO: pause when implemented
        self._state.play()

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

    def _on_tempo_changed(self, value: float) -> None:
        self._state.tempo_factor = value

    def _on_stereo_changed(self, index: int) -> None:
        self._state.stereo_mode = "maestro" if index == 0 else "band_layout"

    def _on_position_changed(self, position_sec: float) -> None:
        dur = self._state.duration_sec
        if dur > 0:
            self._scrub_slider.blockSignals(True)
            self._scrub_slider.setValue(int(1000 * position_sec / dur))
            self._scrub_slider.blockSignals(False)
        self._pos_label.setText(f"{_format_time(position_sec)} / {_format_time(dur)}")

    def _update_ui(self) -> None:
        playing = self._state.is_playing
        self._play_btn.setText(_icon_char("⏸") + " Pause" if playing else _icon_char("▶") + " Play")
        self._vol_slider.blockSignals(True)
        self._vol_slider.setValue(int(self._state.volume))
        self._vol_slider.blockSignals(False)
        self._tempo_spin.blockSignals(True)
        self._tempo_spin.setValue(self._state.tempo_factor)
        self._tempo_spin.blockSignals(False)
        self._stereo_combo.blockSignals(True)
        self._stereo_combo.setCurrentIndex(0 if self._state.stereo_mode == "maestro" else 1)
        self._stereo_combo.blockSignals(False)

    def _on_dropdown_toggled(self, checked: bool) -> None:
        if checked:
            if self._dropdown_panel is None:
                self._build_dropdown_panel()
            if self._dropdown_popup:
                pos = self._dropdown_btn.mapToGlobal(QPoint(0, self._dropdown_btn.height()))
                self._dropdown_popup.move(pos)
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
