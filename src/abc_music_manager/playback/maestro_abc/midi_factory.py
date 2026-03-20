"""
Create MIDI events via mido. Returns (tick, message) for track building.
From MidiFactory.java.
"""

from __future__ import annotations

from typing import Tuple, Union

import mido
from mido import Message, MetaMessage

from .key_mode import KeyMode
from .key_signature import KeySignature
from .midi_constants import (
    CHANNEL_VOLUME_CONTROLLER_COARSE,
    CHORUS_CONTROL,
    META_END_OF_TRACK,
    META_KEY_SIGNATURE,
    META_TEMPO,
    META_TIME_SIGNATURE,
    META_TRACK_NAME,
    PAN_CONTROL,
    REVERB_CONTROL,
)
from .time_signature import TimeSignature


def create_tempo_event(mpqn: int, tick: int) -> Tuple[int, MetaMessage]:
    """Microseconds per quarter note."""
    return (tick, MetaMessage("set_tempo", tempo=mpqn, time=0))


def create_track_name_event(name: str, tick: int = 0) -> Tuple[int, MetaMessage]:
    data = name.encode("ascii", errors="replace")
    return (tick, MetaMessage("track_name", name=name, time=0))


def create_program_change_event(patch: int, channel: int, tick: int) -> Tuple[int, Message]:
    return (tick, Message("program_change", program=patch, channel=channel, time=0))


def create_note_on_event(note_id: int, channel: int, velocity: int, tick: int) -> Tuple[int, Message]:
    return (tick, Message("note_on", note=note_id, velocity=velocity, channel=channel, time=0))


def create_note_off_event(note_id: int, channel: int, velocity: int, tick: int) -> Tuple[int, Message]:
    return (tick, Message("note_off", note=note_id, velocity=velocity, channel=channel, time=0))


def create_pan_event(value: int, channel: int, tick: int = 0) -> Tuple[int, Message]:
    return create_controller_event(PAN_CONTROL, value, channel, tick)


def create_controller_event(controller: int, value: int, channel: int, tick: int) -> Tuple[int, Message]:
    return (
        tick,
        Message("control_change", control=controller, value=value, channel=channel, time=0),
    )


def create_channel_volume_event(volume: int, channel: int, tick: int) -> Tuple[int, Message]:
    if volume < 0 or volume > 127:
        raise ValueError("Volume must be 0-127")
    return create_controller_event(CHANNEL_VOLUME_CONTROLLER_COARSE, volume, channel, tick)


def create_reverb_control_event(value: int, channel: int, tick: int) -> Tuple[int, Message]:
    return create_controller_event(REVERB_CONTROL, value, channel, tick)


def create_chorus_control_event(value: int, channel: int, tick: int) -> Tuple[int, Message]:
    return create_controller_event(CHORUS_CONTROL, value, channel, tick)


def create_time_signature_event(meter: TimeSignature, tick: int) -> Tuple[int, MetaMessage]:
    return (tick, MetaMessage("time_signature", numerator=meter.numerator, denominator=meter.denominator, time=0))


def _key_signature_to_mido_key(key: KeySignature) -> str:
    """Convert KeySignature to mido key string (e.g. 'C', 'Am', 'F#')."""
    if not is_supported_midi_key_mode(key.mode):
        raise ValueError("MIDI key signature only supports major/minor")
    keys_major = ["Cb", "Gb", "Db", "Ab", "Eb", "Bb", "F", "C", "G", "D", "A", "E", "B", "F#", "C#"]
    keys_minor = ["Ab", "Eb", "Bb", "F", "C", "G", "D", "A", "E", "B", "F#", "C#", "G#", "D#", "A#"]
    idx = key.sharps_flats + 7
    base = keys_minor[idx] if key.mode == KeyMode.MINOR else keys_major[idx]
    return base + "m" if key.mode == KeyMode.MINOR else base


def create_key_signature_event(key: KeySignature, tick: int) -> Tuple[int, MetaMessage]:
    mido_key = _key_signature_to_mido_key(key)
    return (tick, MetaMessage("key_signature", key=mido_key, time=0))


def is_supported_midi_key_mode(mode: KeyMode) -> bool:
    return mode in (KeyMode.MAJOR, KeyMode.MINOR)


def create_end_of_track_event(tick: int) -> Tuple[int, MetaMessage]:
    return (tick, MetaMessage("end_of_track", time=0))


def bpm_to_mpqn(bpm: int) -> int:
    """Convert BPM to microseconds per quarter note."""
    return 60_000_000 // bpm
