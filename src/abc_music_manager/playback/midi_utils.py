"""
MIDI utilities: tempo scaling, PPQN normalization for playback.
"""

from __future__ import annotations

import io

import mido

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
