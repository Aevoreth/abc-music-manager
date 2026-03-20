"""Unit tests for midi_utils (tempo scaling) and MidiPlayer helpers."""

import io
import sys
from pathlib import Path

import mido
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from abc_music_manager.playback.midi_utils import normalize_midi_ppqn, scale_midi_tempo
from abc_music_manager.playback.midi_player import _part_mutes_to_muted_channels


def test_normalize_midi_ppqn() -> None:
    """normalize_midi_ppqn converts to 480 PPQN; identity when already 480."""
    # Create minimal 480-PPQN MIDI (division 0x01e0 = 480)
    midi_480 = b"MThd\x00\x00\x00\x06\x00\x00\x00\x01\x01\xe0MTrk\x00\x00\x00\x0b\x00\xff\x51\x03\x07\xa1\x20\x00\xff\x2f\x00"
    result = normalize_midi_ppqn(midi_480)
    assert result == midi_480
    # High-PPQN MIDI (e.g. from ABC L:1/1875000) gets normalized
    from abc_music_manager.playback import abc_to_midi
    abc = "X:1\nM:4/4\nQ:128\nK:C\nL:1/1875000\nc2 d2 e2 f2 |"
    raw = abc_to_midi(abc)
    mf = mido.MidiFile(file=io.BytesIO(raw))
    assert mf.ticks_per_beat != 480
    norm = normalize_midi_ppqn(raw)
    mf_norm = mido.MidiFile(file=io.BytesIO(norm))
    assert mf_norm.ticks_per_beat == 480
    assert abs(mf.length - mf_norm.length) < 0.1  # duration preserved


def test_scale_midi_tempo_identity() -> None:
    """tempo_factor=1.0 returns unchanged bytes."""
    midi = b"MThd\x00\x00\x00\x06\x00\x00\x00\x01\x00\x60MTrk\x00\x00\x00\x0b\x00\xff\x51\x03\x07\xa1\x20\x00\xff\x2f\x00"
    result = scale_midi_tempo(midi, 1.0)
    assert result == midi


def test_scale_midi_tempo_faster() -> None:
    """tempo_factor=2.0 halves mpqn (faster playback)."""
    midi = b"MThd\x00\x00\x00\x06\x00\x00\x00\x01\x00\x60MTrk\x00\x00\x00\x0b\x00\xff\x51\x03\x07\xa1\x20\x00\xff\x2f\x00"
    result = scale_midi_tempo(midi, 2.0)
    assert result != midi
    assert len(result) > 0


def test_part_mutes_to_muted_channels() -> None:
    """Part numbers map to correct MIDI channels."""
    # part 1 -> ch 0, part 2 -> ch 1, ..., part 9 -> ch 8, part 10 -> ch 10
    assert _part_mutes_to_muted_channels({}) == frozenset()
    assert _part_mutes_to_muted_channels({1: True}) == frozenset({0})
    assert _part_mutes_to_muted_channels({2: True}) == frozenset({1})
    assert _part_mutes_to_muted_channels({9: True}) == frozenset({8})
    assert _part_mutes_to_muted_channels({10: True}) == frozenset({10})
    assert _part_mutes_to_muted_channels({1: True, 3: True}) == frozenset({0, 2})
    assert _part_mutes_to_muted_channels({1: False, 2: True}) == frozenset({1})  # only muted
