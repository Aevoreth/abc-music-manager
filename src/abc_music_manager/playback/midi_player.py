"""
TinySoundFont-based MIDI playback. Load, play, pause, stop, panic, volume, seek.
"""

from __future__ import annotations

import io
import threading
import time
from pathlib import Path
from typing import Callable, Optional

import mido

from .midi_utils import normalize_midi_ppqn, scale_midi_tempo


def _part_mutes_to_muted_channels(part_mutes: dict[int, bool]) -> frozenset[int]:
    """Convert part_number -> muted to set of muted MIDI channels."""
    return frozenset(
        part_num - 1 if part_num <= 9 else part_num
        for part_num, muted in part_mutes.items()
        if muted
    )


def _make_mute_filter(muted_channels: frozenset[int]) -> Callable:
    """Return filter that drops NoteOn/NoteOff for muted channels."""

    def filter_fn(event) -> bool | None:
        import tinysoundfont.midi as tsf_midi
        if event.channel not in muted_channels:
            return False  # keep
        action = event.action
        if isinstance(action, (tsf_midi.NoteOn, tsf_midi.NoteOff)):
            return True  # delete
        return False  # keep (e.g. ProgramChange, ControlChange)

    return filter_fn


class MidiPlayer:
    """
    Play MIDI via TinySoundFont. Requires soundfont path.
    Thread-safe for play/stop from UI thread.
    """

    def __init__(self, soundfont_path: str | Path) -> None:
        self._sf_path = Path(soundfont_path)
        if not self._sf_path.is_file():
            raise FileNotFoundError(f"Soundfont not found: {self._sf_path}")
        self._synth = None  # tinysoundfont.Synth
        self._seq = None  # tinysoundfont.Sequencer
        self._midi_bytes: Optional[bytes] = None
        self._duration_sec: float = 0.0
        self._lock = threading.Lock()
        self._volume: float = 0.5  # 0-1, mapped to dB
        self._is_paused: bool = False
        self._paused_at_time: float = 0.0
        self._playing_since: Optional[float] = None
        self._stopped: bool = True

    # Headroom to avoid clipping when many channels play at once (e.g. full arrangements)
    _HEADROOM_DB = -6.0

    def _volume_to_db(self, vol: float) -> float:
        """Map 0-1 to attenuation: 1.0 -> 0 dB, 0.5 -> -6 dB, 0.1 -> -20 dB."""
        if vol <= 0:
            return -48.0  # effectively silent
        import math
        return 20.0 * math.log10(max(0.001, vol))

    def _ensure_synth(self):
        import tinysoundfont
        with self._lock:
            if self._synth is None:
                gain_db = self._volume_to_db(self._volume) + self._HEADROOM_DB
                self._synth = tinysoundfont.Synth(gain=gain_db, samplerate=44100)
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

    def play(
        self,
        midi_bytes: Optional[bytes] = None,
        part_mutes: Optional[dict[int, bool]] = None,
        tempo_factor: float = 1.0,
    ) -> tuple[bool, str]:
        """
        Start playback. Uses midi_bytes if provided, else previously loaded.
        part_mutes: part_number -> muted (filter NoteOn/NoteOff for muted channels).
        tempo_factor: 0.5-2.0, scales playback speed.
        Returns (success, error_message). error_message is empty on success.
        """
        data = midi_bytes or self._midi_bytes
        if not data:
            return False, "No MIDI data"
        self._midi_bytes = data

        # Normalize PPQN so TinySoundFont handles timing correctly (fixes parts repeating / not playing)
        data = normalize_midi_ppqn(data)

        # Apply tempo scaling
        if abs(tempo_factor - 1.0) >= 1e-6:
            data = scale_midi_tempo(data, tempo_factor)

        self._duration_sec = self._get_duration_sec(data)
        if self._duration_sec <= 0:
            return False, "Invalid or empty MIDI file"

        try:
            import tinysoundfont
            synth = self._ensure_synth()
            # New Sequencer per play to avoid leftover events
            self._seq = tinysoundfont.Sequencer(synth)

            # Load MIDI with part mutes filter
            muted = _part_mutes_to_muted_channels(part_mutes or {})
            filter_fn = _make_mute_filter(muted) if muted else None
            events = tinysoundfont.midi.load_memory(data, filter=filter_fn, persistent=True)
            self._seq.add(events)

            synth.start(buffer_size=4096)
            self._stopped = False
            self._is_paused = False
            self._playing_since = time.monotonic()
            return True, ""
        except Exception as e:
            return False, str(e)

    def pause(self) -> None:
        """Pause playback."""
        with self._lock:
            if self._seq and not self._stopped and not self._is_paused:
                self._paused_at_time = self._seq.get_time()
                self._seq.pause(True)
                self._seq.sounds_off()
                self._is_paused = True

    def resume(self) -> None:
        """Resume playback."""
        with self._lock:
            if self._seq and not self._stopped and self._is_paused:
                self._seq.pause(False)
                self._is_paused = False

    def stop(self) -> None:
        """Stop playback. Safe to call multiple times."""
        with self._lock:
            self._playing_since = None
            self._stopped = True
            self._is_paused = False
            if self._synth:
                try:
                    if self._seq:
                        self._seq.sounds_off()
                    self._synth.stop()
                except Exception:
                    pass
    def panic(self) -> None:
        """MIDI panic: all notes off on all channels."""
        with self._lock:
            if self._synth:
                try:
                    self._synth.sounds_off()
                except Exception:
                    pass

    def stop_and_panic(self) -> None:
        """Stop playback and send MIDI panic."""
        self.stop()
        self.panic()

    def seek(self, position_sec: float) -> None:
        """Seek to position. Only valid when loaded and (playing or paused)."""
        with self._lock:
            if not self._seq or self._stopped:
                return
            pos = max(0.0, min(position_sec, self._duration_sec))
            try:
                self._seq.sounds_off()
                self._seq.set_time(pos)
                if self._is_paused:
                    self._paused_at_time = pos
            except Exception:
                pass

    def set_volume(self, value: float) -> None:
        """Set volume 0-1. Applied on next synth creation; use control_change for live adjustment."""
        self._volume = max(0.0, min(1.0, value))
        if self._synth:
            try:
                db = self._volume_to_db(self._volume)
                # TinySoundFont Synth has no runtime gain setter; use MIDI volume on all channels
                vol_midi = int(127 * max(0.0, min(1.0, value)))
                for ch in range(16):
                    self._synth.control_change(ch, 7, vol_midi)
            except Exception:
                pass

    def get_position_sec(self) -> float:
        """Current position in seconds."""
        with self._lock:
            if self._playing_since is None:
                return 0.0
            if self._is_paused and self._seq:
                return min(max(0.0, self._paused_at_time), self._duration_sec)
            if self._seq:
                return min(max(0.0, self._seq.get_time()), self._duration_sec)
            return 0.0

    def get_duration_sec(self) -> float:
        """Total duration in seconds."""
        return self._duration_sec

    def is_playing(self) -> bool:
        """True if playing (not paused, not stopped)."""
        with self._lock:
            if self._stopped or self._playing_since is None:
                return False
            if self._is_paused:
                return False
            if self._seq and self._seq.is_empty():
                return False
            return True

    def is_paused(self) -> bool:
        """True if paused."""
        return self._is_paused

    def close(self) -> None:
        """Release resources."""
        self.stop()
        with self._lock:
            if self._synth:
                try:
                    self._synth.stop()
                except Exception:
                    pass
                self._synth = None
                self._seq = None
