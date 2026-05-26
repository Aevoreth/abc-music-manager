"""Unit and integration tests for maestro_abc ABC-to-MIDI conversion."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from abc_music_manager.playback.maestro_abc import maestro_abc_to_midi as abc_to_midi
from abc_music_manager.playback.maestro_abc.tune_info import TuneInfo
from abc_music_manager.playback.maestro_abc.time_signature import (
    TimeSignature,
    safe_time_signature,
    parse_time_signature,
)
from abc_music_manager.playback.maestro_abc.key_signature import KeySignature
from abc_music_manager.playback.maestro_abc.exceptions import AbcParseError


# --- TuneInfo unit tests ---


def test_tune_info_meter() -> None:
    info = TuneInfo()
    info.set_meter("4/4")
    ts = info.get_meter()
    assert ts.numerator == 4
    assert ts.denominator == 4


def test_tune_info_meter_c() -> None:
    info = TuneInfo()
    info.set_meter("C")
    ts = info.get_meter()
    assert ts.numerator == 4
    assert ts.denominator == 4


def test_tune_info_tempo() -> None:
    info = TuneInfo()
    info.set_primary_tempo_bpm("120")
    assert info.get_primary_tempo_bpm() == 120


def test_tune_info_key() -> None:
    info = TuneInfo()
    info.set_key("G")
    ks = info.get_key()
    assert ks.sharps_flats == 1
    assert ks.mode.name == "MAJOR"


def test_tune_info_ppqn() -> None:
    info = TuneInfo()
    info.set_meter("4/4")
    info.set_note_divisor("1/4")
    ppqn = info.get_ppqn()
    assert ppqn > 0


def test_tune_info_compound_meter() -> None:
    info = TuneInfo()
    info.set_meter("6/8")
    assert info.is_compound_meter() is True
    info.set_meter("4/4")
    assert info.is_compound_meter() is False


# --- Time signature unit tests ---


def test_safe_time_signature_power_of_2() -> None:
    ts = safe_time_signature(4, 4)
    assert ts.numerator == 4
    assert ts.denominator == 4


def test_safe_time_signature_non_power_of_2() -> None:
    """Non-power-of-2 denominator (e.g. 5/6) should return 4/4 for MIDI meta."""
    ts = safe_time_signature(5, 6)
    assert ts.numerator == 4
    assert ts.denominator == 4


def test_parse_time_signature() -> None:
    ts = parse_time_signature("3/4")
    assert ts.numerator == 3
    assert ts.denominator == 4


# --- Integration: minimal ABC → MIDI ---


def test_minimal_abc_to_midi() -> None:
    abc = """
X:1
M:4/4
K:C
L:1/4
C D E F | G A B c | c B A G | F E D C
"""
    midi = abc_to_midi(abc)
    assert len(midi) > 0
    assert midi[:4] == b"MThd"
    assert b"MTrk" in midi


def test_abc_to_midi_with_file_path() -> None:
    abc = "X:1\nM:4/4\nK:C\nL:1/4\nC D E F\n"
    midi = abc_to_midi(abc, file_path="test.abc")
    assert len(midi) > 0


def test_abc_complex_meter_7_8() -> None:
    """Regression: M:7/8 should not raise KeyError."""
    abc = """
X:1
M:7/8
K:C
L:1/8
C D E F G A B
"""
    midi = abc_to_midi(abc)
    assert len(midi) > 0


def test_abc_complex_meter_12_8() -> None:
    """Regression: M:12/8 should not raise KeyError."""
    abc = """
X:1
M:12/8
K:C
L:1/8
C D E F G A B c d e f g
"""
    midi = abc_to_midi(abc)
    assert len(midi) > 0


def test_abc_empty_raises() -> None:
    with pytest.raises(AbcParseError, match="no notes"):
        abc_to_midi("X:1\nM:4/4\nK:C\n")


def test_abc_chord() -> None:
    abc = """
X:1
M:4/4
K:C
L:1/4
[CEG] [CEG]
"""
    midi = abc_to_midi(abc)
    assert len(midi) > 0


def test_abc_tuplet() -> None:
    abc = """
X:1
M:4/4
K:C
L:1/4
(3 C D E
"""
    midi = abc_to_midi(abc)
    assert len(midi) > 0


def test_abc_dynamics_fff_ppp() -> None:
    """+fff+ and +ppp+ should parse correctly (matcher must not treat 'f' in +fff+ as a note)."""
    abc_fff = """
X:1
M:4/4
K:C
L:1/4
+fff+ C D E F
"""
    abc_ppp = """
X:1
M:4/4
K:C
L:1/4
+ppp+ C D E F
"""
    assert len(abc_to_midi(abc_fff)) > 0
    assert len(abc_to_midi(abc_ppp)) > 0


def test_abc_part_name_and_made_for() -> None:
    abc = """
X:1
%%part-name Lute
%%made-for Lute of Ages
M:4/4
K:C
L:1/4
C D E F
"""
    midi = abc_to_midi(abc)
    assert len(midi) > 0


def test_abc_hand_knells_instrument() -> None:
    """Hand-knells should use Glockenspiel (MIDI program 9)."""
    import io
    import mido
    abc = """
X:1
%%part-name Jaunty Hand-knells
M:4/4
K:C
L:1/4
C D E F
"""
    midi_bytes = abc_to_midi(abc)
    assert len(midi_bytes) > 0
    mf = mido.MidiFile(file=io.BytesIO(midi_bytes))
    programs = [msg.program for track in mf.tracks for msg in track if msg.type == "program_change"]
    assert 9 in programs, f"Expected program 9 (Glockenspiel) for hand-knells, got {programs}"


def _note_on_velocities(midi_bytes: bytes) -> list[int]:
    """Return note_on velocities (>0) in track order."""
    import io
    import mido
    mf = mido.MidiFile(file=io.BytesIO(midi_bytes))
    return [
        msg.velocity
        for track in mf.tracks
        for msg in track
        if msg.type == "note_on" and msg.velocity > 0
    ]


def _first_note_on_velocity(midi_bytes: bytes) -> int:
    velocities = _note_on_velocities(midi_bytes)
    assert velocities, "Expected at least one note_on event"
    return velocities[0]


@pytest.mark.parametrize(
    "part_name",
    [
        "Lute of Ages",
        "Basic Lute",
        "Basic Harp",
        "Bardic Fiddle",
        "Sprightly Fiddle",
    ],
)
def test_instrument_velocity_at_mf_matches_maestro(part_name: str) -> None:
    """At +mf+, all instruments share the same MIDI velocity (Maestro abc_vol=106)."""
    abc = f"""
X:1
%%part-name {part_name}
M:4/4
K:C
L:1/4
+mf+ C
"""
    assert _first_note_on_velocity(abc_to_midi(abc)) == 106


@pytest.mark.parametrize(
    ("dynamic", "expected_velocity"),
    [
        ("pppp", 57),
        ("ppp", 61),
        ("mf", 106),
        ("fff", 127),
    ],
)
def test_dynamics_velocity_ladder(dynamic: str, expected_velocity: int) -> None:
    abc = f"""
X:1
M:4/4
K:C
L:1/4
+{dynamic}+ C
"""
    assert _first_note_on_velocity(abc_to_midi(abc)) == expected_velocity


def test_multi_part_same_dynamic_equal_velocities() -> None:
    """Different instruments at +mf+ should produce equal note velocities."""
    abc = """
X:1
%%part-name Lute of Ages
M:4/4
K:C
L:1/4
+mf+ C |

X:2
%%part-name Basic Harp
+mf+ E |
"""
    velocities = _note_on_velocities(abc_to_midi(abc))
    assert len(velocities) >= 2
    assert velocities[0] == 106
    assert velocities[1] == 106


def _first_note_on_off_ticks(midi_bytes: bytes) -> tuple[int, int, int]:
    """Return (note_on_tick, note_off_tick, note_number) for the first played note."""
    import io
    import mido
    mf = mido.MidiFile(file=io.BytesIO(midi_bytes))
    on_tick: int | None = None
    note_num: int | None = None
    for track in mf.tracks:
        abs_tick = 0
        for msg in track:
            abs_tick += msg.time
            if msg.type == "note_on" and msg.velocity > 0 and on_tick is None:
                on_tick = abs_tick
                note_num = msg.note
            elif on_tick is not None and (
                (msg.type == "note_off")
                or (msg.type == "note_on" and msg.velocity == 0)
            ):
                if msg.note == note_num:
                    return on_tick, abs_tick, note_num
    raise AssertionError("Expected a note_on/note_off pair")


def test_drum_note_off_uses_sample_duration_not_extra_hold() -> None:
    """
    Basic Drum uses noteDurations.txt sample length (Maestro handleNoteTie),
    not written note length + 1.5s hold.
    """
    from abc_music_manager.playback.lotro_sample_duration import get_sample_duration_micros

    abc = """
X:1
%%part-name Basic Drum
M:4/4
Q:120
K:C
L:1/4
C,
"""
    midi_bytes = abc_to_midi(abc)
    on_tick, off_tick, note_num = _first_note_on_off_ticks(midi_bytes)
    assert note_num == 36

    length_micros = get_sample_duration_micros("Basic Drum", 36)
    assert length_micros == 954694

    mf = __import__("mido").MidiFile(file=__import__("io").BytesIO(midi_bytes))
    ppqn = mf.ticks_per_beat
    mpqn = 500_000  # 120 BPM
    expected_duration_ticks = int(length_micros * ppqn / mpqn)
    actual_duration_ticks = off_tick - on_tick

    assert actual_duration_ticks == expected_duration_ticks
    # Old behavior added 1.5s hold on top of quarter-note length (~46080 ticks at this PPQN).
    assert actual_duration_ticks < 30_000
