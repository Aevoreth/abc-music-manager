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

from .midi_utils import extract_pan_per_channel, prepare_midi_for_playback

MAX_PARTS = 24  # LOTRO supports up to 24 parts


def _part_index_to_midi_channel(part_index: int) -> int:
    """
    Map part index (0-based order) to virtual MIDI channel. Matches abc_to_midi
    port+channel mapping: parts 1-9 -> ch 0-8, 10-15 -> ch 10-15, 16-24 -> ch 16-23.
    """
    track_num = part_index + 1
    if track_num <= 9:
        return track_num - 1
    if track_num <= 15:
        return track_num  # skip channel 9 (drums)
    return 16 + (track_num - 16)  # port 1: ch 16-23


def _part_mutes_to_muted_channels(part_mutes: dict[int, bool]) -> frozenset[int]:
    """Return set of muted MIDI channels. Keys are part indices (for tests)."""
    return frozenset(
        _part_index_to_midi_channel(i) for i, m in part_mutes.items() if m and 0 <= i < MAX_PARTS
    )


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


def _channel_to_part_index(virtual_ch: int) -> int | None:
    """Reverse of _part_index_to_midi_channel. Ch 9 is reserved for drums (unused)."""
    if virtual_ch <= 8:
        return virtual_ch
    if virtual_ch == 9:
        return None  # drums, no part
    if virtual_ch <= 15:
        return virtual_ch - 1  # ch 10->9, ..., 15->14
    if virtual_ch <= 24:
        return 15 + (virtual_ch - 16)  # ch 16->15, ..., 24->23
    return None


# All virtual channels we use (0-8, 10-15, 16-24). tinysoundfont's sounds_off()
# only touches 0-15, so we must explicitly silence 16-24 when switching songs.
_ALL_CHANNELS = [*range(9), *range(10, 16), *range(16, 25)]


def _sounds_off_all_channels(synth) -> None:
    """Silence all channels we use, including 16-24. tinysoundfont's sounds_off() only does 0-15."""
    for ch in _ALL_CHANNELS:
        if ch in synth.channel:
            try:
                synth.sounds_off(ch)
            except Exception:
                pass


def _apply_part_mutes_to_synth(synth, part_mutes: dict[int, bool], unmuted_volume: int) -> None:
    """
    Apply part mutes via MIDI CC 7 (volume) and notes_off per channel.
    part_mutes key = part index (0-based order). Supports up to 24 parts.
    Virtual channels: 0-8, 10-15, 16-24 (ch 9 reserved for drums).
    Only touches channels that are assigned (synth.channel).
    """
    for vch in _ALL_CHANNELS:
        if vch not in synth.channel:
            continue
        part_idx = _channel_to_part_index(vch)
        if part_idx is None:
            continue
        muted = part_mutes.get(part_idx, False)
        if muted:
            synth.control_change(vch, 7, 0)
            synth.notes_off(vch)
        else:
            synth.control_change(vch, 7, unmuted_volume)


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
                sfid = self._synth.sfload(str(self._sf_path))
                # Pre-assign channels 16-24 for 24-part LOTRO support.
                # tinysoundfont only pre-assigns 0-15 on sfload; parts 16-24 use virtual ch 16-24.
                # Use direct dict assignment to avoid C-level validation that may reject ch>15.
                for ch in range(16, 25):
                    self._synth.channel[ch] = sfid
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
        part_mutes: part index (0-23) -> muted, by part order in ABC (applied via CC7).
        tempo_factor: 0.5-2.0, scales playback speed.
        Returns (success, error_message). error_message is empty on success.
        """
        data = midi_bytes or self._midi_bytes
        if not data:
            return False, "No MIDI data"

        # Single-pass: normalize PPQN, scale tempo, extract events and pan (replaces 5 parses)
        prepared_bytes, events, pan_map, duration_sec = prepare_midi_for_playback(
            data,
            tempo_factor=tempo_factor,
            filter=_strip_volume_cc_filter,
            persistent=True,
        )
        self._midi_bytes = prepared_bytes
        self._duration_sec = duration_sec
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
                        _sounds_off_all_channels(synth)
                        # Reset controllers (sustain, expression, etc.) so they don't bleed into next song
                        for ch in _ALL_CHANNELS:
                            if ch in synth.channel:
                                synth.control_change(ch, 121, 0)  # ALL_CTRL_OFF
                        synth.stop()
                    except Exception:
                        pass
            # New Sequencer per play to avoid leftover events
            self._seq = tinysoundfont.Sequencer(synth)

            self._seq.add(events)

            self._part_mutes = dict(part_mutes or {})
            unmuted_vol = int(127 * max(0.001, self._volume))
            _apply_part_mutes_to_synth(synth, self._part_mutes, unmuted_vol)

            # Apply pan explicitly so stereo positioning is respected (TinySoundFont may not
            # apply pan from MIDI events correctly)
            for ch, pan in pan_map.items():
                synth.control_change(ch, 10, pan)

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
                if self._synth:
                    _sounds_off_all_channels(self._synth)
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
                    _sounds_off_all_channels(self._synth)
                    self._synth.stop()
                except Exception:
                    pass

    def panic(self) -> None:
        """MIDI panic: all notes off on all channels."""
        with self._lock:
            if self._synth:
                try:
                    _sounds_off_all_channels(self._synth)
                except Exception:
                    pass

    def stop_and_panic(self) -> None:
        """Stop playback and send MIDI panic."""
        self.stop()
        self.panic()

    def seek(self, position_sec: float) -> None:
        """Seek to position. Only valid when loaded and (playing or paused)."""
        with self._lock:
            if not self._seq or self._stopped or not self._synth:
                return
            pos = max(0.0, min(position_sec, self._duration_sec))
            try:
                self._seq.sounds_off()
                _sounds_off_all_channels(self._synth)
                self._seq.set_time(pos)
                if self._is_paused:
                    self._paused_at_time = pos
                # Re-apply pan after seek; TinySoundFont may reset controller state
                for ch, pan in extract_pan_per_channel(self._midi_bytes).items():
                    self._synth.control_change(ch, 10, pan)
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
                if self._midi_bytes:
                    for ch, pan in extract_pan_per_channel(self._midi_bytes).items():
                        self._synth.control_change(ch, 10, pan)
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
