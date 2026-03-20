"""
TinySoundFont-based MIDI playback. Load, play, pause, stop, panic, volume, seek.
"""

from __future__ import annotations

import io
import threading
import time
from pathlib import Path
from typing import Optional

import mido

from .midi_utils import normalize_midi_ppqn, scale_midi_tempo


def _part_index_to_midi_channel(part_index: int) -> int:
    """
    Map part index (0-based order) to MIDI channel. Matches abc_to_midi._get_track_channel:
    channel 9 is reserved for drums, so parts 1-9 -> ch 0-8, part 10 -> ch 10, etc.
    """
    track_num = part_index + 1
    if track_num < 10:
        return track_num - 1
    return track_num  # skip channel 9


def _part_mutes_to_muted_channels(part_mutes: dict[int, bool]) -> frozenset[int]:
    """Return set of muted MIDI channels. Keys are part indices (for tests)."""
    return frozenset(_part_index_to_midi_channel(i) for i, m in part_mutes.items() if m and 0 <= i < 16)


def _strip_volume_cc_filter(event) -> bool | None:
    """
    Filter that drops CC 7 (channel volume) events from MIDI load.
    We control volume ourselves via set_part_mutes/set_volume, so the
    ABC's volume events would overwrite our mutes.
    """
    import tinysoundfont.midi as tsf_midi
    if isinstance(event.action, tsf_midi.ControlChange) and event.action.control == 7:
        return True  # delete
    return False  # keep


def _apply_part_mutes_to_synth(synth, part_mutes: dict[int, bool], unmuted_volume: int) -> None:
    """
    Apply part mutes via MIDI CC 7 (volume) and notes_off per channel.
    part_mutes key = part index (0-based order). Map to MIDI channel (skip ch 9).
    We strip CC 7 from MIDI, so we must set volume for all channels.
    """
    for ch in range(16):
        # Reverse mapping: which part index uses this channel?
        part_idx = ch if ch < 9 else ch - 1  # ch 9 unused, so ch 10 -> part 9
        muted = part_mutes.get(part_idx, False)
        if muted:
            synth.control_change(ch, 7, 0)
            synth.notes_off(ch)  # immediately stop any sounding notes
        else:
            synth.control_change(ch, 7, unmuted_volume)


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
        self._part_mutes: dict[int, bool] = {}
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
        part_mutes: channel_index (0-15) -> muted, by part order in ABC (applied via CC7).
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
            # Stop previous playback and clear state before starting new song.
            # Prevents tempo drift, stuck MIDI events, and decay tails from previous song.
            with self._lock:
                if self._seq:
                    try:
                        self._seq.sounds_off()
                    except Exception:
                        pass
                    self._seq = None
                if synth:
                    try:
                        synth.sounds_off()
                        # Reset controllers (sustain, expression, etc.) so they don't bleed into next song
                        for ch in range(16):
                            synth.control_change(ch, 121, 0)  # ALL_CTRL_OFF
                        synth.stop()
                    except Exception:
                        pass
            # New Sequencer per play to avoid leftover events
            self._seq = tinysoundfont.Sequencer(synth)

            # Strip CC 7 (volume) from MIDI so our mute/set_volume control stays in effect
            events = tinysoundfont.midi.load_memory(data, filter=_strip_volume_cc_filter, persistent=True)
            self._seq.add(events)

            self._part_mutes = dict(part_mutes or {})
            unmuted_vol = int(127 * max(0.001, self._volume))
            _apply_part_mutes_to_synth(synth, self._part_mutes, unmuted_vol)

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
                vol_midi = int(127 * max(0.001, self._volume))
                _apply_part_mutes_to_synth(self._synth, self._part_mutes, vol_midi)
            except Exception:
                pass

    def set_part_mutes(self, part_mutes: dict[int, bool]) -> None:
        """
        Update part mutes in real-time during playback.
        Uses CC 7 (volume) and notes_off per channel.
        """
        self._part_mutes = dict(part_mutes or {})
        if self._synth:
            try:
                unmuted_vol = int(127 * max(0.001, self._volume))
                _apply_part_mutes_to_synth(self._synth, self._part_mutes, unmuted_vol)
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
