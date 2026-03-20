"""
Playback state: playlist, part mutes, volume, tempo, stereo. Qt signals for UI.
"""

from __future__ import annotations

import multiprocessing
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, Signal, QTimer, QThread

from ..playback import resolve_soundfont_path, MidiPlayer
from ..playback.convert_worker import run_conversion
from . import preferences


class _ConversionWorker(QThread):
    """Background thread: spawn subprocess for ABC conversion (avoids GIL blocking main thread)."""

    finished_ok = Signal(object)  # bytes
    finished_error = Signal(str)

    def __init__(self, file_path: str, stereo_slider: int = 100, parent=None) -> None:
        super().__init__(parent)
        self._file_path = file_path
        self._stereo_slider = stereo_slider

    def run(self) -> None:
        result_queue: multiprocessing.Queue = multiprocessing.Queue()
        proc = multiprocessing.Process(
            target=run_conversion,
            args=(self._file_path, result_queue),
            kwargs={"stereo": self._stereo_slider},
        )
        proc.start()
        try:
            ok, data = result_queue.get(timeout=120)
        except Exception:
            proc.terminate()
            proc.join(timeout=5)
            ok, data = False, "Conversion timed out (2 minutes)"
        proc.join(timeout=2)
        if proc.is_alive():
            proc.terminate()
            proc.join(timeout=1)
        if ok:
            self.finished_ok.emit(data)
        else:
            self.finished_error.emit(data)


@dataclass
class PlaylistEntry:
    """A song in the playlist."""

    song_id: int
    file_path: str
    title: str
    source: str  # "library" | "setlist" | "set_playback"


class PlaybackState(QObject):
    """
    Central playback state. Emits signals for UI updates.
    Requires soundfont; use ensure_soundfont() before play.
    """

    position_changed = Signal(float)  # position_sec
    state_changed = Signal()  # is_playing, current_song, etc.
    playlist_changed = Signal()
    soundfont_missing = Signal()  # prompt user to locate/download
    playback_failed = Signal(str)  # error message when conversion fails

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._player: Optional[MidiPlayer] = None
        self._playlist: list[PlaylistEntry] = []
        self._current_index: int = -1
        self._part_mutes: dict[int, bool] = {}  # part_number -> muted
        self._active_band_layout_id: Optional[int] = None
        self._active_song_layout_id: Optional[int] = None
        self._position_timer = QTimer(self)
        self._position_timer.timeout.connect(self._on_position_tick)
        self._position_timer.setInterval(100)  # 10 Hz
        self._conversion_worker: Optional[_ConversionWorker] = None
        self._conversion_cancelled = False
        self._load_prefs()

    def _load_prefs(self) -> None:
        """Load playback settings from preferences."""
        self._volume = preferences.get_playback_volume() / 100.0  # 0-1 for MidiPlayer
        self._tempo_factor = preferences.get_playback_tempo()
        self._stereo_mode = preferences.get_playback_stereo_mode()
        self._stereo_slider = preferences.get_playback_stereo_slider()

    def _save_prefs(self) -> None:
        """Persist playback settings."""
        preferences.set_playback_volume(self._volume * 100.0)
        preferences.set_playback_tempo(self._tempo_factor)
        preferences.set_playback_stereo_mode(self._stereo_mode)
        preferences.set_playback_stereo_slider(self._stereo_slider)

    def ensure_soundfont(self) -> Optional[Path]:
        """
        Resolve soundfont path. Returns Path if found, None otherwise.
        If None, emits soundfont_missing for UI to prompt.
        """
        user_path = preferences.get_playback_soundfont_path()
        path = resolve_soundfont_path(user_path or None)
        if path is None:
            self.soundfont_missing.emit()
        return path

    def _ensure_player(self) -> Optional[MidiPlayer]:
        """Create MidiPlayer if soundfont available. Returns None if not."""
        if self._player is not None:
            return self._player
        path = self.ensure_soundfont()
        if path is None:
            return None
        try:
            self._player = MidiPlayer(path)
            self._player.set_volume(self._volume)
            return self._player
        except Exception as e:
            self.playback_failed.emit(
                f"Could not initialize audio: {e}\n\n"
                "Ensure TinySoundFont and PyAudio are installed. "
                "Run: pip install tinysoundfont pyaudio"
            )
            return None

    @property
    def current_song_id(self) -> Optional[int]:
        if 0 <= self._current_index < len(self._playlist):
            return self._playlist[self._current_index].song_id
        return None

    @property
    def current_file_path(self) -> Optional[str]:
        if 0 <= self._current_index < len(self._playlist):
            return self._playlist[self._current_index].file_path
        return None

    @property
    def is_playing(self) -> bool:
        return self._player is not None and self._player.is_playing()

    @property
    def is_paused(self) -> bool:
        return self._player is not None and self._player.is_paused()

    @property
    def position_sec(self) -> float:
        return self._player.get_position_sec() if self._player else 0.0

    @property
    def duration_sec(self) -> float:
        return self._player.get_duration_sec() if self._player else 0.0

    @property
    def volume(self) -> float:
        return self._volume * 100.0

    @volume.setter
    def volume(self, value: float) -> None:
        self._volume = max(0.0, min(100.0, value)) / 100.0
        if self._player:
            self._player.set_volume(self._volume)
        self._save_prefs()
        self.state_changed.emit()

    @property
    def tempo_factor(self) -> float:
        return self._tempo_factor

    @tempo_factor.setter
    def tempo_factor(self, value: float) -> None:
        self._tempo_factor = max(0.25, min(4.0, value))
        self._save_prefs()
        self.state_changed.emit()

    @property
    def stereo_mode(self) -> str:
        return self._stereo_mode

    @stereo_mode.setter
    def stereo_mode(self, value: str) -> None:
        self._stereo_mode = value if value in ("maestro", "band_layout") else "maestro"
        self._save_prefs()
        self.state_changed.emit()

    @property
    def stereo_slider(self) -> int:
        return self._stereo_slider

    @stereo_slider.setter
    def stereo_slider(self, value: int) -> None:
        self._stereo_slider = max(0, min(100, value))
        self._save_prefs()
        self.state_changed.emit()

    @property
    def part_mutes(self) -> dict[int, bool]:
        return dict(self._part_mutes)

    def set_part_muted(self, part_number: int, muted: bool) -> None:
        self._part_mutes[part_number] = muted
        self.state_changed.emit()

    @property
    def playlist(self) -> list[PlaylistEntry]:
        return list(self._playlist)

    @property
    def current_index(self) -> int:
        return self._current_index

    @property
    def active_band_layout_id(self) -> Optional[int]:
        return self._active_band_layout_id

    @active_band_layout_id.setter
    def active_band_layout_id(self, value: Optional[int]) -> None:
        self._active_band_layout_id = value
        self.state_changed.emit()

    @property
    def active_song_layout_id(self) -> Optional[int]:
        return self._active_song_layout_id

    @active_song_layout_id.setter
    def active_song_layout_id(self, value: Optional[int]) -> None:
        self._active_song_layout_id = value
        self.state_changed.emit()

    def replace_playlist(self, entries: list[PlaylistEntry], start_index: int = 0) -> None:
        """Replace playlist and optionally start playing at start_index."""
        self.stop()
        self._playlist = list(entries)
        self._current_index = min(start_index, len(self._playlist) - 1) if self._playlist else -1
        self._part_mutes.clear()
        self.playlist_changed.emit()
        self.state_changed.emit()
        if self._playlist and self._current_index >= 0:
            self.play()

    def add_to_playlist(self, entries: list[PlaylistEntry]) -> None:
        """Append to playlist without starting playback."""
        self._playlist.extend(entries)
        self.playlist_changed.emit()
        self.state_changed.emit()

    def remove_from_playlist(self, index: int) -> None:
        """Remove playlist entry at index."""
        if 0 <= index < len(self._playlist):
            self._playlist.pop(index)
            if self._current_index >= len(self._playlist):
                self._current_index = len(self._playlist) - 1
            elif index < self._current_index:
                self._current_index -= 1
            self.playlist_changed.emit()
            self.state_changed.emit()

    def reorder_playlist(self, indices: list[int]) -> None:
        """Reorder playlist by new indices. indices[i] = old index of item at new position i."""
        if len(indices) != len(self._playlist):
            return
        new_playlist = [self._playlist[i] for i in indices]
        old_current = self._current_index
        self._playlist = new_playlist
        self._current_index = indices.index(old_current) if old_current in indices else -1
        self.playlist_changed.emit()
        self.state_changed.emit()

    def play(self) -> bool:
        """Start playback of current playlist item. Conversion runs in background to avoid UI freeze."""
        if not self._playlist or self._current_index < 0:
            return False
        player = self._ensure_player()
        if player is None:
            return False
        if self._player and self._player.is_paused():
            self._player.resume()
            self._position_timer.start()
            self.state_changed.emit()
            return True
        if self._conversion_worker is not None and self._conversion_worker.isRunning():
            return True  # Already converting
        self._conversion_cancelled = False
        entry = self._playlist[self._current_index]
        self._conversion_worker = _ConversionWorker(
            entry.file_path, stereo_slider=self._stereo_slider, parent=self
        )
        self._conversion_worker.finished_ok.connect(self._on_conversion_done)
        self._conversion_worker.finished_error.connect(self._on_conversion_error)
        self._conversion_worker.finished_ok.connect(self._conversion_worker.deleteLater)
        self._conversion_worker.finished_error.connect(self._conversion_worker.deleteLater)
        self._conversion_worker.start()
        self.state_changed.emit()
        return True

    def _on_conversion_done(self, midi_bytes: bytes) -> None:
        self._conversion_worker = None
        if self._conversion_cancelled or not self._player or not self._playlist or self._current_index < 0:
            return
        ok, err = self._player.play(
            midi_bytes,
            part_mutes=self._part_mutes,
            tempo_factor=self._tempo_factor,
        )
        if ok:
            self._position_timer.start()
        else:
            self.playback_failed.emit(
                f"Playback failed: {err}" if err else "TinySoundFont could not start. Check soundfont in Settings."
            )
        self.state_changed.emit()

    def _on_conversion_error(self, message: str) -> None:
        self._conversion_worker = None
        self.playback_failed.emit(message)
        self.state_changed.emit()

    def stop(self) -> None:
        """Stop playback."""
        self._position_timer.stop()
        if self._conversion_worker is not None:
            self._conversion_cancelled = True
            worker = self._conversion_worker
            self._conversion_worker = None
            if worker.isRunning():
                worker.wait(10000)  # Wait up to 10s to avoid "QThread destroyed while running"
            if worker.isRunning():
                worker.setParent(None)  # Orphan so parent destroy won't kill running thread
            else:
                worker.deleteLater()
        if self._player:
            self._player.stop()
        self.state_changed.emit()

    def pause(self) -> None:
        """Pause playback."""
        self._position_timer.stop()
        if self._player:
            self._player.pause()
        self.state_changed.emit()

    def resume(self) -> None:
        """Resume playback."""
        if self._player and self._player.is_paused():
            self._player.resume()
            self._position_timer.start()
        self.state_changed.emit()

    def panic(self) -> None:
        """MIDI panic then stop. Cancels conversion worker like stop() to avoid QThread crash."""
        self._position_timer.stop()
        if self._conversion_worker is not None:
            self._conversion_cancelled = True
            worker = self._conversion_worker
            self._conversion_worker = None
            if worker.isRunning():
                worker.wait(10000)
            if worker.isRunning():
                worker.setParent(None)
            else:
                worker.deleteLater()
        if self._player:
            try:
                self._player.stop_and_panic()
            except Exception:
                pass
        self.state_changed.emit()

    def _on_position_tick(self) -> None:
        if self._player and not self._player.is_playing() and not self._player.is_paused():
            self._position_timer.stop()
            self._advance_to_next()
            return
        self.position_changed.emit(self.position_sec)

    def _advance_to_next(self) -> None:
        """Move to next playlist item; play if available. Same flow as song ending naturally."""
        if self._current_index < len(self._playlist) - 1:
            self._current_index += 1
            self.state_changed.emit()
            self.play()
        else:
            self.state_changed.emit()

    def next_track(self) -> None:
        """
        Skip to next track. Triggers same end-of-song MIDI cleanup as natural end:
        stop current (sounds_off), then advance to next and play.
        """
        if not self._playlist:
            return
        self._position_timer.stop()
        if self._player:
            try:
                self._player.stop()  # Same as song ending: stop, sounds_off
            except Exception:
                pass
        if self._current_index < len(self._playlist) - 1:
            self._current_index += 1
            self.state_changed.emit()
            self.play()
        else:
            self.state_changed.emit()

    def previous_track_or_rewind(self, seconds_since_last_prev: float) -> bool:
        """
        First click: rewind to beginning. Second click within 1 second: previous song.
        Returns True if we went to previous (or restarted), False if just rewound.
        """
        if not self._playlist:
            return False
        if seconds_since_last_prev < 1.0 and self._current_index > 0:
            # Second click within 1s: go to previous track
            self._position_timer.stop()
            if self._player:
                try:
                    self._player.stop()
                except Exception:
                    pass
            self._current_index -= 1
            self.state_changed.emit()
            self.play()
            return True
        # First click or >1s: rewind to start
        self.seek(0.0)
        return False

    def seek(self, position_sec: float) -> None:
        """Seek to position."""
        if self._player:
            self._player.seek(position_sec)
            self.position_changed.emit(self.position_sec)

    def close(self) -> None:
        """Release resources."""
        self.stop()
        if self._player:
            self._player.close()
            self._player = None
