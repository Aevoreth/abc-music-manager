"""
Playback state: playlist, part mutes, volume, tempo, stereo. Qt signals for UI.
"""

from __future__ import annotations

import json
import multiprocessing
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import QObject, Signal, QTimer, QThread

from ..playback import resolve_soundfont_path, MidiPlayer
from ..playback.convert_worker import run_conversion
from . import preferences


class _ConversionWorker(QThread):
    """Background thread: spawn subprocess for ABC conversion (avoids GIL blocking main thread)."""

    finished_ok = Signal(object)  # bytes
    finished_error = Signal(str)

    def __init__(
        self,
        file_path: str,
        stereo_slider: int = 100,
        stereo_mode: str = "maestro",
        part_pan_map: Optional[dict[int, int]] = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._file_path = file_path
        self._stereo_slider = stereo_slider
        self._stereo_mode = (
            stereo_mode
            if stereo_mode in ("band_layout", "maestro_user_pan", "maestro")
            else "maestro"
        )
        self._part_pan_map = part_pan_map

    def run(self) -> None:
        result_queue: multiprocessing.Queue = multiprocessing.Queue()
        proc = multiprocessing.Process(
            target=run_conversion,
            args=(self._file_path, result_queue),
            kwargs={
                "stereo": self._stereo_slider,
                "stereo_mode": self._stereo_mode,
                "part_pan_map": self._part_pan_map,
            },
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
    song_layout_id: Optional[int] = None  # for band_layout stereo when from setlist
    band_layout_id: Optional[int] = None  # for band_layout stereo when from setlist
    setlist_item_id: Optional[int] = None  # setlist item id for SetlistBandAssignment overrides


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
    layout_used = Signal(int, int, int, object)  # song_id, band_layout_id, song_layout_id, setlist_item_id|None

    def __init__(
        self,
        parent: QObject | None = None,
        *,
        get_part_pan_map: Optional[
            Callable[
                [Optional[int], Optional[int], Optional[int]],
                Optional[dict[int, int]],
            ]
        ] = None,
    ) -> None:
        super().__init__(parent)
        self._player: Optional[MidiPlayer] = None
        self._playlist: list[PlaylistEntry] = []
        self._current_index: int = -1
        self._part_mutes: dict[int, bool] = {}  # part_number -> muted
        self._active_band_layout_id: Optional[int] = None
        self._active_song_layout_id: Optional[int] = None
        # User-selected layout from toolbar dropdown. None=use context; () = (none)/fallback; (bl_id, sl_id, item_id?) = use this
        self._layout_override: Optional[tuple] = None
        self._position_timer = QTimer(self)
        self._position_timer.timeout.connect(self._on_position_tick)
        self._position_timer.setInterval(100)  # 10 Hz
        self._conversion_worker: Optional[_ConversionWorker] = None
        self._conversion_cancelled = False
        self._pending_seek_sec: Optional[float] = None
        self._pending_was_paused = False
        self._get_part_pan_map = get_part_pan_map
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
        # #region agent log
        try:
            from pathlib import Path
            lp = Path.cwd() / "debug-58ac41.log"
            with open(lp, "a") as f:
                f.write(json.dumps({"sessionId":"58ac41","location":"playback_state.py:ensure_soundfont","message":"Soundfont resolution","data":{"resolved":str(path) if path else None,"user_path":user_path},"hypothesisId":"B","timestamp":__import__("time").time()*1000})+'\n')
        except Exception:
            pass
        # #endregion
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
        old_factor = self._tempo_factor
        self._tempo_factor = max(0.5, min(2.0, value))
        self._save_prefs()
        # If playing or paused, restart with new tempo from current position
        if self._player and (self.is_playing or self.is_paused):
            pos = self._player.get_position_sec()
            was_paused = self._player.is_paused()
            ok, _ = self._player.play(
                part_mutes=self._part_mutes,
                tempo_factor=self._tempo_factor,
            )
            if ok:
                # Seek to equivalent position (position in sec scales with tempo change)
                new_pos = pos * old_factor / self._tempo_factor
                self._player.seek(new_pos)
                if was_paused:
                    self._player.pause()
                self._position_timer.start()
        self.state_changed.emit()

    @property
    def stereo_mode(self) -> str:
        return self._stereo_mode

    @stereo_mode.setter
    def stereo_mode(self, value: str) -> None:
        self._stereo_mode = (
            value
            if value in ("band_layout", "maestro_user_pan", "maestro")
            else "maestro"
        )
        self._save_prefs()
        if self._player and (self.is_playing or self.is_paused):
            from PySide6.QtCore import QTimer
            QTimer.singleShot(0, self.restart_current_with_new_stereo)
        self.state_changed.emit()

    @property
    def stereo_slider(self) -> int:
        return self._stereo_slider

    @stereo_slider.setter
    def stereo_slider(self, value: int) -> None:
        self._stereo_slider = max(0, min(100, value))
        self._save_prefs()
        if self._player and (self.is_playing or self.is_paused):
            # Defer restart to next event loop tick so stereo_slider is committed and
            # we avoid re-entrancy from valueChanged during drag; use same path as
            # band layout change so pan is correctly applied after reconversion.
            from PySide6.QtCore import QTimer
            QTimer.singleShot(0, self.restart_current_with_new_stereo)
        self.state_changed.emit()

    @property
    def part_mutes(self) -> dict[int, bool]:
        return dict(self._part_mutes)

    def set_part_muted(self, channel_index: int, muted: bool) -> None:
        """channel_index: 0-based part order (matches MIDI channel for that part)."""
        self._part_mutes[channel_index] = muted
        if self._player and (self.is_playing or self.is_paused):
            self._player.set_part_mutes(self._part_mutes)
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

    def set_layout_override(
        self,
        override: Optional[tuple] | None,
    ) -> None:
        """
        Set user-selected layout from toolbar dropdown.
        None = use context (entry/active).
        () = user chose (none), fall back to user-pan/maestro.
        (band_layout_id, song_layout_id, setlist_item_id?) = use this layout.
        """
        self._layout_override = override
        self.state_changed.emit()

    def get_layout_override(self) -> Optional[tuple]:
        """Current layout override: None, (), or (bl_id, sl_id, item_id?)."""
        return self._layout_override

    def get_active_band_layout_id(self) -> Optional[int]:
        """Band layout ID currently used for stereo pan (when stereo_mode is band_layout). None if not using band layout."""
        if self._stereo_mode != "band_layout":
            return None
        if not self._playlist or self._current_index < 0:
            return None
        entry = self._playlist[self._current_index]
        ov = self._layout_override
        if ov == ():
            return None
        if ov is not None and len(ov) >= 1:
            return ov[0]
        return entry.band_layout_id or self._active_band_layout_id

    def get_active_song_layout_id(self) -> Optional[int]:
        """Song layout ID currently used for stereo pan (when stereo_mode is band_layout). None if not using band layout."""
        if self._stereo_mode != "band_layout":
            return None
        if not self._playlist or self._current_index < 0:
            return None
        entry = self._playlist[self._current_index]
        ov = self._layout_override
        if ov == ():
            return None
        if ov is not None and len(ov) >= 2:
            return ov[1]
        return entry.song_layout_id or self._active_song_layout_id

    def get_active_setlist_item_id(self) -> Optional[int]:
        """Setlist item ID currently used for stereo pan (when playing from setlist with band_layout). None otherwise."""
        if self._stereo_mode != "band_layout":
            return None
        if not self._playlist or self._current_index < 0:
            return None
        entry = self._playlist[self._current_index]
        ov = self._layout_override
        if ov == ():
            return None
        if ov is not None and len(ov) >= 3 and ov[2] is not None:
            return ov[2]
        return entry.setlist_item_id

    def restart_current_with_new_stereo(self) -> None:
        """Restart current track to pick up new stereo/pan (e.g. after band layout slots changed)."""
        if not self._playlist or self._current_index < 0:
            return
        if self._player and (self.is_playing or self.is_paused):
            pos = self._player.get_position_sec()
            was_paused = self._player.is_paused()
            self.stop()
            self._pending_seek_sec = pos
            self._pending_was_paused = was_paused
            self.play()

    def replace_playlist(self, entries: list[PlaylistEntry], start_index: int = 0) -> None:
        """Replace playlist and optionally start playing at start_index."""
        self.stop()
        self._playlist = list(entries)
        self._current_index = min(start_index, len(self._playlist) - 1) if self._playlist else -1
        self._part_mutes.clear()
        # Clear layout override so toolbar derives layout from source (Library vs setlist) on next refresh
        self._layout_override = None
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
        part_pan_map: Optional[dict[int, int]] = None
        # Always compute part_pan_map when we have setlist layout data, so switching
        # to band_layout mid-song (reconvert) produces correct pan.
        if self._get_part_pan_map is not None:
            ov = self._layout_override
            if ov == ():
                # User chose (none) in dropdown: fall back to user-pan/maestro
                bl_id = None
                sl_id = None
                setlist_item_id = None
            elif ov is not None and len(ov) >= 2:
                bl_id, sl_id = ov[0], ov[1]
                setlist_item_id = ov[2] if len(ov) > 2 else None
            else:
                sl_id = entry.song_layout_id or self._active_song_layout_id
                bl_id = entry.band_layout_id or self._active_band_layout_id
                setlist_item_id = entry.setlist_item_id
            if bl_id:
                part_pan_map = self._get_part_pan_map(sl_id, bl_id, setlist_item_id)
                if bl_id and sl_id:
                    self.layout_used.emit(entry.song_id, bl_id, sl_id, setlist_item_id)
            if part_pan_map is None and bl_id:
                import os
                import sys
                if os.environ.get("ABC_PAN_DEBUG") == "1":
                    print(
                        f"[pan] get_part_pan_map returned None (sl={sl_id}, bl={bl_id}, item={setlist_item_id})",
                        file=sys.stderr,
                        flush=True,
                    )
        self._conversion_worker = _ConversionWorker(
            entry.file_path,
            stereo_slider=self._stereo_slider,
            stereo_mode=self._stereo_mode,
            part_pan_map=part_pan_map,
            parent=self,
        )
        self._conversion_worker.finished_ok.connect(self._on_conversion_done)
        self._conversion_worker.finished_error.connect(self._on_conversion_error)
        self._conversion_worker.finished_ok.connect(self._conversion_worker.deleteLater)
        self._conversion_worker.finished_error.connect(self._conversion_worker.deleteLater)
        self._conversion_worker.start()
        self.state_changed.emit()
        return True

    def _on_conversion_done(self, midi_bytes: bytes) -> None:
        # #region agent log
        try:
            import json
            from pathlib import Path
            with open(Path.cwd() / "debug-58ac41.log", "a") as f:
                f.write(json.dumps({"sessionId":"58ac41","location":"playback_state.py:_on_conversion_done","message":"Conversion complete","data":{"len_bytes":len(midi_bytes) if midi_bytes else 0},"hypothesisId":"C","timestamp":__import__("time").time()*1000})+'\n')
        except Exception:
            pass
        # #endregion
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
            if self._pending_seek_sec is not None:
                pos = self._pending_seek_sec
                was_paused = self._pending_was_paused
                self._pending_seek_sec = None
                self._pending_was_paused = False
                self._player.seek(pos)
                if was_paused:
                    self._player.pause()
                    self._position_timer.stop()
        else:
            self._pending_seek_sec = None
            self._pending_was_paused = False
            self.playback_failed.emit(
                f"Playback failed: {err}" if err else "TinySoundFont could not start. Check soundfont in Settings."
            )
        self.state_changed.emit()

    def _on_conversion_error(self, message: str) -> None:
        self._conversion_worker = None
        self._pending_seek_sec = None
        self._pending_was_paused = False
        self.playback_failed.emit(message)
        self.state_changed.emit()

    def stop(self) -> None:
        """Stop playback."""
        # #region agent log
        try:
            import json
            from pathlib import Path
            w = self._conversion_worker
            with open(Path.cwd() / "debug-58ac41.log", "a") as f:
                f.write(json.dumps({"sessionId":"58ac41","location":"playback_state.py:stop","message":"Stop entry","data":{"worker_running":w.isRunning() if w else False},"hypothesisId":"D","timestamp":__import__("time").time()*1000})+'\n')
        except Exception:
            pass
        # #endregion
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
        # #region agent log
        try:
            import json
            from pathlib import Path
            with open(Path.cwd() / "debug-58ac41.log", "a") as f:
                f.write(json.dumps({"sessionId":"58ac41","location":"playback_state.py:stop","message":"Stop exit","data":{},"hypothesisId":"D","timestamp":__import__("time").time()*1000})+'\n')
        except Exception:
            pass
        # #endregion
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
            self._part_mutes.clear()  # New song = fresh mutes
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
            self._part_mutes.clear()
            self.state_changed.emit()
            self.play()
        else:
            self.state_changed.emit()

    def go_to_index(self, index: int) -> None:
        """Jump to playlist item at index and start playing."""
        if not self._playlist or index < 0 or index >= len(self._playlist):
            return
        self._position_timer.stop()
        if self._player:
            try:
                self._player.stop()
            except Exception:
                pass
        self._current_index = index
        self._part_mutes.clear()
        self.state_changed.emit()
        self.play()

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
            self._part_mutes.clear()
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
        # #region agent log
        try:
            import json
            from pathlib import Path
            with open(Path.cwd() / "debug-58ac41.log", "a") as f:
                f.write(json.dumps({"sessionId":"58ac41","location":"playback_state.py:close","message":"Close entry","data":{},"hypothesisId":"D","timestamp":__import__("time").time()*1000})+'\n')
        except Exception:
            pass
        # #endregion
        self.stop()
        if self._player:
            self._player.close()
            self._player = None
        # #region agent log
        try:
            import json
            from pathlib import Path
            with open(Path.cwd() / "debug-58ac41.log", "a") as f:
                f.write(json.dumps({"sessionId":"58ac41","location":"playback_state.py:close","message":"Close exit","data":{},"hypothesisId":"D","timestamp":__import__("time").time()*1000})+'\n')
        except Exception:
            pass
        # #endregion
