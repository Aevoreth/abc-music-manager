"""
FluidSynth-based MIDI playback. Load, play, pause, stop, panic, volume.
"""

from __future__ import annotations

import io
import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Optional

import mido

_FLUIDSYNTH_DEFAULT_PATH = "C:\\tools\\fluidsynth\\bin"


def _get_synth_class():
    """Import FluidSynth, redirecting hardcoded path if user has configured one."""
    try:
        user_path = None
        try:
            from ..services import preferences
            user_path = preferences.get_playback_fluidsynth_bin_path()
        except Exception:
            pass

        if user_path and Path(user_path).is_dir():
            norm = lambda p: str(p).rstrip("\\/").replace("/", "\\").lower()
            patched = False
            if hasattr(os, "add_dll_directory"):
                _orig_add_dll = os.add_dll_directory

                def _patched_add_dll(path):
                    if norm(path) == norm(_FLUIDSYNTH_DEFAULT_PATH):
                        return _orig_add_dll(user_path)
                    return _orig_add_dll(path)

                os.add_dll_directory = _patched_add_dll
                patched = True
            # Ensure find_library can locate the DLL
            path_env = os.environ.get("PATH", "")
            if user_path not in path_env:
                os.environ["PATH"] = user_path + os.pathsep + path_env
            try:
                from fluidsynth import Synth
                return Synth
            finally:
                if patched:
                    os.add_dll_directory = _orig_add_dll
        else:
            from fluidsynth import Synth
            return Synth
    except (ImportError, OSError) as e:
        raise RuntimeError(
            f"FluidSynth not available: {e}\n\n"
            "Set the FluidSynth bin path in Settings > Playback (folder containing libfluidsynth DLL). "
            "Download from https://github.com/FluidSynth/fluidsynth/releases"
        ) from e


class MidiPlayer:
    """
    Play MIDI via FluidSynth. Requires soundfont path.
    Thread-safe for play/stop from UI thread.
    """

    def __init__(self, soundfont_path: str | Path) -> None:
        self._sf_path = Path(soundfont_path)
        if not self._sf_path.is_file():
            raise FileNotFoundError(f"Soundfont not found: {self._sf_path}")
        self._synth: Optional[Synth] = None
        self._current_file: Optional[Path] = None
        self._midi_bytes: Optional[bytes] = None
        self._duration_sec: float = 0.0
        self._start_time: float = 0.0
        self._paused_at: float = 0.0
        self._lock = threading.Lock()
        self._volume: float = 0.5  # 0-1
        self._playing_since: Optional[float] = None  # monotonic time when play started
        self._player_stopped: bool = True  # avoid calling play_midi_stop twice (crashes)

    def _ensure_synth(self):
        with self._lock:
            if self._synth is None:
                Synth = _get_synth_class()
                # Windows: prefer dsound for audio (avoids SDL3/WASAPI device issues)
                import sys
                settings = {}
                if sys.platform == "win32":
                    settings["audio.driver"] = "dsound"
                self._synth = Synth(gain=self._volume, **settings)
                self._synth.start()
                self._synth.sfload(str(self._sf_path))
            return self._synth

    def _get_duration_sec(self, midi_bytes: bytes) -> float:
        """Get duration in seconds from MIDI file."""
        try:
            f = mido.MidiFile(file=io.BytesIO(midi_bytes))
            return f.length
        except Exception:
            return 0.0

    def load(self, midi_bytes: bytes) -> None:
        """Load MIDI for playback. Does not start playing."""
        self._midi_bytes = midi_bytes
        self._duration_sec = self._get_duration_sec(midi_bytes)


    def play(self, midi_bytes: Optional[bytes] = None) -> tuple[bool, str]:
        """
        Start playback. Uses midi_bytes if provided, else previously loaded.
        Returns (success, error_message). error_message is empty on success.
        """
        data = midi_bytes or self._midi_bytes
        if not data:
            return False, "No MIDI data"
        self._midi_bytes = data
        self._duration_sec = self._get_duration_sec(data)

        if self._duration_sec <= 0:
            return False, "Invalid or empty MIDI file"

        try:
            synth = self._ensure_synth()
            with tempfile.NamedTemporaryFile(suffix=".mid", delete=False) as f:
                f.write(data)
                self._current_file = Path(f.name)
            try:
                synth.play_midi_file(str(self._current_file))
                self._player_stopped = False
                self._start_time = time.monotonic()
                self._playing_since = self._start_time
                self._paused_at = 0.0
                return True, ""
            except Exception as e:
                self._current_file.unlink(missing_ok=True)
                raise
        except Exception as e:
            return False, str(e)

    def stop(self) -> None:
        """Stop playback. Safe to call multiple times."""
        with self._lock:
            was_playing = not self._player_stopped
            self._playing_since = None
            self._player_stopped = True
            if self._synth and was_playing:
                try:
                    # Silence immediately (fluid_player_stop can lag)
                    for ch in range(16):
                        try:
                            self._synth.all_sounds_off(ch)
                        except Exception:
                            pass
                    if hasattr(self._synth, "player") and self._synth.player is not None:
                        try:
                            self._synth.play_midi_stop()
                        finally:
                            # pyfluidsynth deletes the player but doesn't clear the ref - avoid dangling use
                            setattr(self._synth, "player", None)
                except Exception:
                    pass
            if self._current_file and self._current_file.exists():
                self._current_file.unlink(missing_ok=True)
                self._current_file = None

    def panic(self) -> None:
        """MIDI panic: all notes off on all channels."""
        with self._lock:
            if self._synth:
                for ch in range(16):
                    try:
                        self._synth.all_sounds_off(ch)
                    except Exception:
                        pass

    def stop_and_panic(self) -> None:
        """Stop playback and send MIDI panic. Same as stop() but ensures silence first."""
        self.stop()  # stop() already does all_sounds_off + play_midi_stop

    def set_volume(self, value: float) -> None:
        """Set volume 0-1."""
        self._volume = max(0.0, min(1.0, value))
        if self._synth:
            self._synth.setting("synth.gain", self._volume)

    def get_position_sec(self) -> float:
        """Estimated position in seconds (elapsed since play start)."""
        if self._playing_since is None:
            return 0.0
        elapsed = time.monotonic() - self._playing_since + self._paused_at
        return min(max(0.0, elapsed), self._duration_sec)

    def get_duration_sec(self) -> float:
        """Total duration in seconds."""
        return self._duration_sec

    def is_playing(self) -> bool:
        """True if currently playing (based on elapsed time vs duration)."""
        if self._playing_since is None:
            return False
        elapsed = time.monotonic() - self._playing_since + self._paused_at
        return elapsed < self._duration_sec

    def close(self) -> None:
        """Release resources."""
        self.stop()
        with self._lock:
            if self._synth:
                try:
                    self._synth.delete()
                except Exception:
                    pass
                self._synth = None
