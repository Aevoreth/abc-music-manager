"""
MIDI utilities: tempo scaling, PPQN normalization, pan extraction for playback.
"""

from __future__ import annotations

import io
import os
from typing import Callable, Optional

import mido

PAN_CC = 0x0A
MAX_VIRTUAL_CHANNELS = 24  # LOTRO supports up to 24 parts; we map port+channel to 0-23

# TinySoundFont mishandles non-standard PPQN (e.g. 11520 from L:1/1875000 ABC).
# Normalize to 480 before playback so events play at correct times.
TARGET_PPQN = 480


def normalize_midi_ppqn(midi_bytes: bytes, target_ppqn: int = TARGET_PPQN) -> bytes:
    """
    Resave MIDI with target_ppqn. Fixes TinySoundFont timing bugs with unusual PPQN.
    Returns modified MIDI bytes, or original on error.
    """
    try:
        midi_file = mido.MidiFile(file=io.BytesIO(midi_bytes))
        old_ppqn = midi_file.ticks_per_beat
        if old_ppqn == target_ppqn:
            return midi_bytes
        scale = target_ppqn / old_ppqn
        out_file = mido.MidiFile(type=midi_file.type, ticks_per_beat=target_ppqn)
        for track in midi_file.tracks:
            new_track = mido.MidiTrack()
            abs_tick = 0
            prev_new_tick = 0
            for msg in track:
                abs_tick += getattr(msg, "time", 0)
                new_abs_tick = max(0, int(abs_tick * scale))
                new_delta = new_abs_tick - prev_new_tick
                prev_new_tick = new_abs_tick
                new_msg = msg.copy(time=new_delta)
                new_track.append(new_msg)
            out_file.tracks.append(new_track)
        out = io.BytesIO()
        out_file.save(file=out)
        return out.getvalue()
    except Exception:
        return midi_bytes


def scale_midi_tempo(midi_bytes: bytes, tempo_factor: float) -> bytes:
    """
    Scale all set_tempo meta messages by tempo_factor.
    Higher tempo_factor = faster playback = lower mpqn.
    Returns modified MIDI bytes.
    """
    if tempo_factor <= 0 or abs(tempo_factor - 1.0) < 1e-6:
        return midi_bytes
    try:
        midi_file = mido.MidiFile(file=io.BytesIO(midi_bytes))
        for track in midi_file.tracks:
            for msg in track:
                if msg.type == "set_tempo":
                    msg.tempo = max(1, int(msg.tempo / tempo_factor))
        out = io.BytesIO()
        midi_file.save(file=out)
        return out.getvalue()
    except Exception:
        return midi_bytes


def _virtual_channel(port: int, channel: int) -> int:
    """Map (port, channel) to virtual channel 0-23 for up to 24 parts."""
    return 16 * port + channel


def extract_pan_per_channel(midi_bytes: bytes) -> dict[int, int]:
    """
    Extract first pan (CC 10) value per MIDI channel. Returns {virtual_channel: pan 0-127}.
    Port-aware: port 1 channel 0 maps to virtual channel 16. Used to apply pan
    explicitly to the synth so TinySoundFont respects stereo positioning.
    """
    result: dict[int, int] = {}
    try:
        midi_file = mido.MidiFile(file=io.BytesIO(midi_bytes))
        for track in midi_file.tracks:
            port = 0
            abs_tick = 0
            for msg in track:
                abs_tick += getattr(msg, "time", 0)
                if msg.type == "midi_port":
                    port = getattr(msg, "port", 0)
                elif msg.type == "control_change" and msg.control == PAN_CC:
                    vch = _virtual_channel(port, msg.channel)
                    if vch not in result:
                        result[vch] = min(127, max(0, msg.value))
    except Exception:
        pass
    if os.environ.get("ABC_PAN_DEBUG") == "1":
        import sys
        print(f"[pan] midi_player extracted pan per channel: {dict(sorted(result.items())) if result else '(none found)'}", file=sys.stderr, flush=True)
    return result


def load_midi_port_aware(
    midi_bytes: bytes,
    filter: Optional[Callable] = None,
    persistent: bool = True,
) -> list:
    """
    Load MIDI with port support for >16 channels. TinySoundFont's loader ignores
    port meta, so we parse with mido and map port+channel to virtual channels 0-23.
    Returns list of tinysoundfont Event objects.
    """
    import tinysoundfont.midi as tsf_midi

    events: list = []
    try:
        midi_file = mido.MidiFile(file=io.BytesIO(midi_bytes))
        ticks_per_beat = midi_file.ticks_per_beat
        tempo_map: list[tuple[int, int]] = [(0, 500_000)]

        # Build tempo map from all tracks (typically track 0 has set_tempo)
        for track in midi_file.tracks:
            abs_tick = 0
            for msg in track:
                abs_tick += getattr(msg, "time", 0)
                if msg.type == "set_tempo":
                    tempo_map.append((abs_tick, msg.tempo))
        tempo_map.sort(key=lambda x: x[0])

        for track in midi_file.tracks:
            port = 0
            abs_tick = 0
            for msg in track:
                abs_tick += getattr(msg, "time", 0)
                if msg.type == "midi_port":
                    port = getattr(msg, "port", 0)
                elif msg.type == "note_on":
                    vch = _virtual_channel(port, msg.channel)
                    t_sec = _tick_to_sec(abs_tick, tempo_map, ticks_per_beat)
                    evt = tsf_midi.Event(
                        tsf_midi.NoteOn(msg.note, msg.velocity),
                        t=t_sec,
                        channel=vch,
                        persistent=persistent,
                    )
                    if filter is None or not filter(evt):
                        events.append(evt)
                elif msg.type == "note_off":
                    vch = _virtual_channel(port, msg.channel)
                    t_sec = _tick_to_sec(abs_tick, tempo_map, ticks_per_beat)
                    evt = tsf_midi.Event(
                        tsf_midi.NoteOff(msg.note),
                        t=t_sec,
                        channel=vch,
                        persistent=persistent,
                    )
                    if filter is None or not filter(evt):
                        events.append(evt)
                elif msg.type == "control_change":
                    vch = _virtual_channel(port, msg.channel)
                    t_sec = _tick_to_sec(abs_tick, tempo_map, ticks_per_beat)
                    evt = tsf_midi.Event(
                        tsf_midi.ControlChange(msg.control, msg.value),
                        t=t_sec,
                        channel=vch,
                        persistent=persistent,
                    )
                    if filter is None or not filter(evt):
                        events.append(evt)
                elif msg.type == "program_change":
                    vch = _virtual_channel(port, msg.channel)
                    t_sec = _tick_to_sec(abs_tick, tempo_map, ticks_per_beat)
                    evt = tsf_midi.Event(
                        tsf_midi.ProgramChange(msg.program),
                        t=t_sec,
                        channel=vch,
                        persistent=persistent,
                    )
                    if filter is None or not filter(evt):
                        events.append(evt)
                elif msg.type == "pitchwheel":
                    vch = _virtual_channel(port, msg.channel)
                    t_sec = _tick_to_sec(abs_tick, tempo_map, ticks_per_beat)
                    evt = tsf_midi.Event(
                        tsf_midi.PitchBend(msg.pitch + 8192),
                        t=t_sec,
                        channel=vch,
                        persistent=persistent,
                    )
                    if filter is None or not filter(evt):
                        events.append(evt)

        events.sort(key=lambda e: e.t)
    except Exception:
        pass
    return events


def _tick_to_sec(tick: int, tempo_map: list[tuple[int, int]], ppqn: int) -> float:
    """Convert absolute tick to seconds using tempo map."""
    if not tempo_map:
        return 0.0
    tempo_map = sorted(tempo_map, key=lambda x: x[0])
    sec = 0.0
    last_tick = 0
    last_tempo = tempo_map[0][1]
    for t, tempo in tempo_map:
        if t > tick:
            break
        sec += (t - last_tick) * last_tempo / (ppqn * 1_000_000)
        last_tick, last_tempo = t, tempo
    sec += (tick - last_tick) * last_tempo / (ppqn * 1_000_000)
    return sec


def prepare_midi_for_playback(
    midi_bytes: bytes,
    *,
    tempo_factor: float = 1.0,
    target_ppqn: int = TARGET_PPQN,
    filter: Optional[Callable] = None,
    persistent: bool = True,
) -> tuple[bytes, list, dict[int, int], float]:
    """
    Single-pass MIDI preparation: normalize PPQN, scale tempo, extract events and pan.
    Returns (final_bytes, events, pan_map, duration_sec). Reduces 5 parses to 1.
    """
    import tinysoundfont.midi as tsf_midi

    events: list = []
    pan_map: dict[int, int] = {}
    duration_sec = 0.0

    try:
        midi_file = mido.MidiFile(file=io.BytesIO(midi_bytes))
        old_ppqn = midi_file.ticks_per_beat
        scale_ppqn = target_ppqn / old_ppqn if old_ppqn != target_ppqn else 1.0
        apply_tempo_scale = tempo_factor > 0 and abs(tempo_factor - 1.0) >= 1e-6

        # Build PPQN-normalized and tempo-scaled structure
        if scale_ppqn != 1.0 or apply_tempo_scale:
            out_file = mido.MidiFile(type=midi_file.type, ticks_per_beat=target_ppqn)
            for track in midi_file.tracks:
                new_track = mido.MidiTrack()
                abs_tick = 0
                prev_new_tick = 0
                for msg in track:
                    abs_tick += getattr(msg, "time", 0)
                    new_abs_tick = max(0, int(abs_tick * scale_ppqn))
                    new_delta = new_abs_tick - prev_new_tick
                    prev_new_tick = new_abs_tick
                    new_msg = msg.copy(time=new_delta)
                    if apply_tempo_scale and new_msg.type == "set_tempo":
                        new_msg.tempo = max(1, int(new_msg.tempo / tempo_factor))
                    new_track.append(new_msg)
                out_file.tracks.append(new_track)
            midi_file = out_file

        ticks_per_beat = midi_file.ticks_per_beat
        tempo_map: list[tuple[int, int]] = [(0, 500_000)]

        for track in midi_file.tracks:
            abs_tick = 0
            for msg in track:
                abs_tick += getattr(msg, "time", 0)
                if msg.type == "set_tempo":
                    tempo_map.append((abs_tick, msg.tempo))
        tempo_map.sort(key=lambda x: x[0])

        for track in midi_file.tracks:
            port = 0
            abs_tick = 0
            for msg in track:
                abs_tick += getattr(msg, "time", 0)
                if msg.type == "midi_port":
                    port = getattr(msg, "port", 0)
                elif msg.type == "control_change":
                    vch = _virtual_channel(port, msg.channel)
                    if msg.control == PAN_CC and vch not in pan_map:
                        pan_map[vch] = min(127, max(0, msg.value))
                    t_sec = _tick_to_sec(abs_tick, tempo_map, ticks_per_beat)
                    evt = tsf_midi.Event(
                        tsf_midi.ControlChange(msg.control, msg.value),
                        t=t_sec,
                        channel=vch,
                        persistent=persistent,
                    )
                    if filter is None or not filter(evt):
                        events.append(evt)
                elif msg.type == "note_on":
                    vch = _virtual_channel(port, msg.channel)
                    t_sec = _tick_to_sec(abs_tick, tempo_map, ticks_per_beat)
                    evt = tsf_midi.Event(
                        tsf_midi.NoteOn(msg.note, msg.velocity),
                        t=t_sec,
                        channel=vch,
                        persistent=persistent,
                    )
                    if filter is None or not filter(evt):
                        events.append(evt)
                elif msg.type == "note_off":
                    vch = _virtual_channel(port, msg.channel)
                    t_sec = _tick_to_sec(abs_tick, tempo_map, ticks_per_beat)
                    evt = tsf_midi.Event(
                        tsf_midi.NoteOff(msg.note),
                        t=t_sec,
                        channel=vch,
                        persistent=persistent,
                    )
                    if filter is None or not filter(evt):
                        events.append(evt)
                elif msg.type == "program_change":
                    vch = _virtual_channel(port, msg.channel)
                    t_sec = _tick_to_sec(abs_tick, tempo_map, ticks_per_beat)
                    evt = tsf_midi.Event(
                        tsf_midi.ProgramChange(msg.program),
                        t=t_sec,
                        channel=vch,
                        persistent=persistent,
                    )
                    if filter is None or not filter(evt):
                        events.append(evt)
                elif msg.type == "pitchwheel":
                    vch = _virtual_channel(port, msg.channel)
                    t_sec = _tick_to_sec(abs_tick, tempo_map, ticks_per_beat)
                    evt = tsf_midi.Event(
                        tsf_midi.PitchBend(msg.pitch + 8192),
                        t=t_sec,
                        channel=vch,
                        persistent=persistent,
                    )
                    if filter is None or not filter(evt):
                        events.append(evt)

        events.sort(key=lambda e: e.t)
        duration_sec = midi_file.length

        out = io.BytesIO()
        midi_file.save(file=out)
        final_bytes = out.getvalue()
    except Exception:
        final_bytes = midi_bytes
        events = []
        pan_map = {}
        duration_sec = 0.0

    if os.environ.get("ABC_PAN_DEBUG") == "1":
        import sys
        print(f"[pan] prepared pan per channel: {dict(sorted(pan_map.items())) if pan_map else '(none)'}", file=sys.stderr, flush=True)

    return (final_bytes, events, pan_map, duration_sec)
