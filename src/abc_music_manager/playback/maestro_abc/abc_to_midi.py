"""
ABC to MIDI conversion. Port of AbcToMidi.java.
"""

from __future__ import annotations

import io
import re
from pathlib import Path
from typing import Optional

import mido
from mido import MetaMessage

from .. import lotro_instruments
from ..lotro_instruments import is_non_sustained_instrument
from ..pan_generator import get_pan as get_maestro_pan
from .abc_constants import (
    DEFAULT_NOTE_TICKS,
    MAX_CHORD_NOTES,
    MIDI_CHORUS,
    MIDI_REVERB,
    NON_SUSTAINED_NOTE_HOLD_SECONDS,
)
from .abc_field import AbcField
from .abc_info import AbcInfo
from .dynamics import Dynamics
from .exceptions import AbcParseError, LotroParseError
from .key_signature import KeySignature
from .midi_constants import DRUM_CHANNEL, MAX_PARTS, MAX_VOLUME
from .midi_factory import (
    bpm_to_mpqn,
    create_channel_volume_event,
    create_chorus_control_event,
    create_end_of_track_event,
    create_key_signature_event,
    create_note_off_event,
    create_note_on_event,
    create_pan_event,
    create_program_change_event,
    create_reverb_control_event,
    create_time_signature_event,
    create_track_name_event,
    create_tempo_event,
    is_supported_midi_key_mode,
)
from .note import MIN_PLAYABLE, MAX_PLAYABLE
from .tune_info import TuneInfo

# Regex from Java
INFO_PATTERN = re.compile(r"^([A-Za-z]):\s*(.*)\s*$")
XINFO_PATTERN = re.compile(r"^\s*%%([A-Za-z\-]+)((:?)|\s)\s*(.*)\s*$")
NOTE_PATTERN = re.compile(
    r"(_{1,2}|=|\^{1,2})?"  # accidental
    r"([xzA-Ga-g])"  # letter
    r"(,{1,5}|'{1,5})?"  # octave
    r"(\d+)?"  # length numerator
    r"(//?\d*)?"  # length denominator
    r"(>{1,3}|<{1,3})?"  # broken rhythm
    r"(-)?"  # tie
)

CHR_NOTE_DELTA = [9, 11, 0, 2, 4, 5, 7]  # a-g -> semitones above C


def _get_track_port_and_channel(track_number: int) -> tuple[int, int]:
    """
    Return (port, channel) for a track. Supports up to 24 parts (LOTRO limit).
    Channel 9 is reserved for drums on port 0.
    Parts 1-15: port 0, channels 0-8 and 10-15.
    Parts 16-24: port 1, channels 0-8.
    """
    if track_number <= 9:
        return (0, track_number - 1)  # ch 0-8
    if track_number <= 15:
        return (0, track_number)  # ch 10-15 (skip 9)
    return (1, track_number - 16)  # port 1, ch 0-8 for parts 16-24


def _get_track_channel(track_number: int) -> int:
    """Legacy: return channel only (port 0). For port 1 tracks, channel is 0-8."""
    _, ch = _get_track_port_and_channel(track_number)
    return ch


def _read_lines(path: str | Path) -> list[str]:
    p = Path(path)
    try:
        return p.read_text(encoding="utf-8", errors="strict").splitlines()
    except UnicodeDecodeError:
        return p.read_text(encoding="cp1252", errors="replace").splitlines()


def _parse_tuplet(s: str, compound_meter: bool) -> tuple[int, int, int]:
    parts = s.split(":")
    if len(parts) < 1 or len(parts) > 3:
        raise ValueError("Invalid tuplet")
    p = int(parts[0])
    if p < 2 or p > 9:
        raise ValueError("Invalid tuplet")
    if len(parts) >= 2 and parts[1]:
        q = int(parts[1])
    elif p in (3, 6):
        q = 2
    elif p in (2, 4, 8):
        q = 3
    elif p in (5, 7, 9):
        q = 3 if compound_meter else 2
    else:
        raise ValueError("Invalid tuplet")
    r = int(parts[2]) if len(parts) >= 3 else p
    return p, q, r


def abc_to_midi(
    abc_content: str,
    file_path: Optional[str | Path] = None,
    *,
    use_lotro_instruments: bool = True,
    enable_lotro_errors: bool = False,
    stereo: int = 100,
    stereo_mode: str = "maestro",
    part_pan_map: Optional[dict[int, int]] = None,
) -> bytes:
    """
    Convert ABC content to MIDI bytes.
    Self-contained port of Maestro's AbcToMidi - handles complex time signatures.
    stereo_mode: 'band_layout', 'maestro_user_pan', or 'maestro'. band_layout uses part_pan_map when provided.
    part_pan_map: part_number (1-based) -> pan (0-127) for band_layout mode.
    """
    filename = Path(file_path).name if file_path else "ABC"
    lines = abc_content.splitlines()

    # FileAndData equivalent
    files_data = [(filename, lines)]

    return _convert(
        files_data=files_data,
        use_lotro_instruments=use_lotro_instruments,
        instrument_override_map=None,
        enable_lotro_errors=enable_lotro_errors,
        stereo=stereo,
        stereo_mode=stereo_mode,
        part_pan_map=part_pan_map,
    )


def _convert(
    files_data: list[tuple[str, list[str]]],
    use_lotro_instruments: bool = True,
    instrument_override_map: Optional[dict[int, int]] = None,
    enable_lotro_errors: bool = False,
    stereo: int = 100,
    stereo_mode: str = "maestro",
    part_pan_map: Optional[dict[int, int]] = None,
) -> bytes:
    abc_info = AbcInfo()
    abc_info.reset()

    info = TuneInfo()
    track_events: dict[int, list[tuple[int, object]]] = {}  # track_idx -> [(tick, msg), ...]
    channel = 0
    track_number = 0
    track_index = 0
    note_divisor_change_line = 0
    chord_start_tick = 0.0
    chord_end_tick = 0.0
    ppqn = 0
    tied_notes: dict[int, int] = {}  # note_id -> (line << 16) | column
    accidentals: dict[int, int] = {}
    note_off_events: list[tuple[int, int, int, int]] = []  # (tick, note_id, channel, velocity)
    line_number_for_regions = -1
    part_start_line = 0

    for file_name, line_list in files_data:
        for line in line_list:
            line_number_for_regions += 1
            line_number = line_number_for_regions + 1

            # Strip comments (% but not %% which is extended info)
            if not line.strip().startswith("%%"):
                comment = line.find("%")
                if comment >= 0:
                    line = line[:comment]
            line = line.strip()
            if not line:
                continue

            # Extended info %%...
            xmatch = XINFO_PATTERN.match(line)
            if xmatch:
                field_str = xmatch.group(1) + (xmatch.group(3) or " ")
                field = AbcField.from_string(field_str)
                value = (xmatch.group(4) or "").strip()
                if field == AbcField.TEMPO:
                    try:
                        info.add_tempo_event(int(chord_start_tick), value)
                    except (ValueError, TypeError):
                        pass
                elif field:
                    abc_info.set_extended_metadata(field, value)
                    if field == AbcField.USER_PAN:
                        abc_info.set_part_user_pan(track_number, value)
                    elif field == AbcField.PART_NAME:
                        info.set_title(value, True)
                        abc_info.set_part_name(track_number, value, True)
                        if not instrument_override_map or track_number not in instrument_override_map:
                            prog = lotro_instruments.resolve_instrument_to_midi_program(value, None)
                            if not info.is_instrument_definitive_set():
                                info.set_instrument(prog, False)
                        abc_info.set_part_instrument(track_number, info.get_instrument_midi_program())
                    elif field == AbcField.MADE_FOR:
                        if not instrument_override_map or track_number not in instrument_override_map:
                            prog = lotro_instruments.resolve_instrument_to_midi_program(None, value)
                            info.set_instrument(prog, True)
                        abc_info.set_part_instrument(track_number, info.get_instrument_midi_program())
                continue

            # Info field X:, T:, K:, L:, M:, Q:
            imatch = INFO_PATTERN.match(line)
            if imatch:
                ftype = imatch.group(1).upper()[0]
                fvalue = imatch.group(2).strip()
                abc_info.set_metadata(ftype, fvalue)
                try:
                    if ftype == "X":
                        if tied_notes:
                            line_col = next(iter(tied_notes.values()))
                            raise AbcParseError(
                                "Tied note does not connect to another note",
                                file_name,
                                line_col >> 16,
                                line_col & 0xFFFF,
                            )
                        accidentals.clear()
                        note_off_events.clear()
                        info.new_part(int(fvalue))
                        track_number += 1
                        part_start_line = line_number
                        chord_start_tick = 0.0
                        chord_end_tick = 0.0
                        abc_info.set_part_number(track_number, info.get_part_number())
                        if instrument_override_map and track_number in instrument_override_map:
                            info.set_instrument(instrument_override_map[track_number], False)
                        abc_info.set_part_instrument(track_number, info.get_instrument_midi_program())
                    elif ftype == "T":
                        info.set_title(fvalue, False)
                        abc_info.set_part_name(track_number, fvalue, False)
                        if not instrument_override_map or track_number not in instrument_override_map:
                            if not info.is_instrument_set():
                                prog = lotro_instruments.resolve_instrument_to_midi_program(fvalue, None)
                                info.set_instrument(prog, False)
                        abc_info.set_part_instrument(track_number, info.get_instrument_midi_program())
                    elif ftype == "K":
                        info.set_key(fvalue)
                    elif ftype == "L":
                        info.set_note_divisor(fvalue)
                        note_divisor_change_line = line_number
                    elif ftype == "M":
                        info.set_meter(fvalue)
                        note_divisor_change_line = line_number
                    elif ftype == "Q":
                        info.set_primary_tempo_bpm(fvalue)
                        abc_info.set_primary_tempo_bpm(info.get_primary_tempo_bpm())
                except (ValueError, TypeError) as e:
                    raise AbcParseError(str(e), file_name, line_number, imatch.start(2))
                continue

            # Note line
            if track_number == 0:
                track_number = 1
                if instrument_override_map and track_number in instrument_override_map:
                    info.set_instrument(instrument_override_map[track_number], False)
                abc_info.set_part_instrument(track_number, info.get_instrument_midi_program())

            if not track_events:
                ppqn = info.get_ppqn()
                abc_info.set_primary_tempo_bpm(info.get_primary_tempo_bpm())
                abc_info.set_part_number(0, 0)
                abc_info.set_part_name(0, info.get_title(), False)
                abc_info.set_time_signature(info.get_meter())
                abc_info.set_key_signature(info.get_key())
                track_events[0] = []

            track_index = track_number
            if track_index not in track_events:
                track_index = len(track_events)
                if track_index > MAX_PARTS:
                    raise AbcParseError(f"Too many parts (max {MAX_PARTS})", file_name, part_start_line)
                _, channel = _get_track_port_and_channel(track_index)
                track_events[track_index] = []
                prog = info.get_instrument_midi_program()
                # Program change
                track_events[track_index].append(
                    (0, create_program_change_event(prog, channel, 0)[1])
                )
                if use_lotro_instruments:
                    track_events[track_index].append(
                        (1, create_channel_volume_event(MAX_VOLUME, channel, 1)[1])
                    )
                    track_events[track_index].append(
                        (1, create_reverb_control_event(MIDI_REVERB, channel, 1)[1])
                    )
                    track_events[track_index].append(
                        (1, create_chorus_control_event(MIDI_CHORUS, channel, 1)[1])
                    )
                abc_info.set_part_instrument(track_number, info.get_instrument_midi_program())

            # Parse notes in line
            in_chord = False
            chord_size = 0
            tuplet: Optional[tuple[int, int, int]] = None
            broken_rhythm_num, broken_rhythm_denom = 1, 1
            i = 0
            while True:
                m = NOTE_PATTERN.search(line, i)
                parse_end = m.start() if m else len(line)
                # Process non-note chars
                while i < parse_end:
                    ch = line[i] if i < len(line) else ""
                    if ch and ch.isspace():
                        if in_chord:
                            raise AbcParseError("Unexpected whitespace inside a chord", file_name, line_number, i)
                        i += 1
                        continue
                    if ch == "[":
                        if in_chord:
                            raise AbcParseError("Unexpected '[' inside a chord", file_name, line_number, i)
                        if broken_rhythm_denom != 1 or broken_rhythm_num != 1:
                            raise AbcParseError("Can't have broken rhythm within a chord", file_name, line_number, i)
                        in_chord = True
                        chord_size = 0
                        i += 1
                        continue
                    if ch == "]":
                        if not in_chord:
                            raise AbcParseError("Unexpected ']'", file_name, line_number, i)
                        in_chord = False
                        chord_start_tick = chord_end_tick
                        i += 1
                        continue
                    if ch == "|":
                        if in_chord:
                            raise AbcParseError("Unexpected '|' inside a chord", file_name, line_number, i)
                        accidentals.clear()
                        if i + 1 < len(line) and line[i + 1] in "]:":
                            i += 1
                        i += 1
                        continue
                    if ch == "+":
                        j = line.find("+", i + 1)
                        if j < 0:
                            raise AbcParseError("No matching '+'", file_name, line_number, i)
                        try:
                            info.set_dynamics(line[i + 1 : j])
                        except ValueError:
                            raise AbcParseError("Unsupported +decoration+", file_name, line_number, i)
                        i = j + 1
                        continue
                    if ch == "(":
                        if i + 1 < len(line) and line[i + 1].isdigit():
                            if tuplet:
                                raise AbcParseError("Unexpected '(' before end of tuplet", file_name, line_number, i)
                            j = i + 1
                            while j < len(line) and (line[j] == ":" or line[j].isdigit()):
                                j += 1
                            tuplet = _parse_tuplet(line[i + 1 : j], info.is_compound_meter())
                            i = j
                        else:
                            if in_chord:
                                raise AbcParseError("Unexpected '(' inside a chord", file_name, line_number, i)
                            i += 1
                        continue
                    if ch == ")":
                        if in_chord:
                            raise AbcParseError("Unexpected ')' inside a chord", file_name, line_number, i)
                        i += 1
                        continue
                    if ch == "\\":
                        i += 1
                        continue
                    if ch and ch not in " \t":
                        raise AbcParseError(f"Unknown character '{ch}'", file_name, line_number, i)
                    i += 1

                if i >= len(line):
                    break
                # The matcher might find +f+, +ff+, or +fff+ and think it's a note
                if not m or i < m.start():
                    i += 1
                    continue
                if i > m.start():
                    continue  # Skip match inside +decoration+

                if in_chord:
                    chord_size += 1
                if enable_lotro_errors and in_chord and chord_size > MAX_CHORD_NOTES:
                    raise LotroParseError("Too many notes in a chord", file_name, line_number, m.start())

                # Parse note
                num = int(m.group(4)) if m.group(4) else 1
                denom_str = m.group(5)
                if not denom_str:
                    denom = 1
                elif denom_str == "/":
                    denom = 2
                elif denom_str == "//":
                    denom = 4
                else:
                    try:
                        denom = int(denom_str[1:])
                    except (ValueError, IndexError):
                        denom = 4

                broken = m.group(6)
                if broken:
                    if broken_rhythm_denom != 1 or broken_rhythm_num != 1:
                        raise AbcParseError("Invalid broken rhythm", file_name, line_number, m.start(6))
                    if in_chord:
                        raise AbcParseError("Can't have broken rhythm within a chord", file_name, line_number, m.start(6))
                    if m.group(7):
                        raise AbcParseError("Tied notes can't have broken rhythms", file_name, line_number, m.start(6))
                    factor = 1 << len(broken)
                    if broken[0] == ">":
                        num *= 2 * factor - 1
                        denom *= factor
                        broken_rhythm_denom = factor
                    else:
                        broken_rhythm_num = 2 * factor - 1
                        broken_rhythm_denom = factor
                        denom *= factor
                else:
                    num *= broken_rhythm_num
                    denom *= broken_rhythm_denom
                    broken_rhythm_num, broken_rhythm_denom = 1, 1

                if tuplet and (not in_chord or chord_size == 1):
                    num *= tuplet[1]
                    denom *= tuplet[0]
                    tuplet = (tuplet[0], tuplet[1], tuplet[2] - 1)
                    if tuplet[2] == 0:
                        tuplet = None

                cur_tempo = info.get_current_tempo_bpm(int(chord_start_tick))
                prim_tempo = info.get_primary_tempo_bpm()
                num *= cur_tempo
                denom *= prim_tempo

                tick_factor = info.get_tick_factor()
                l_num = info.get_l_num()
                l_denom = info.get_l_denom()
                note_end_tick = chord_start_tick + (
                    tick_factor * DEFAULT_NOTE_TICKS * num * l_num / (denom * l_denom)
                )
                if chord_end_tick == chord_start_tick or note_end_tick < chord_end_tick:
                    chord_end_tick = note_end_tick

                letter = m.group(2)[0]
                octave_str = m.group(3) or ""

                if letter in "zx":
                    if not in_chord:
                        chord_start_tick = note_end_tick
                    i = m.end()
                    continue

                octave = 3 if letter.isupper() else 4
                if "'" in octave_str:
                    octave += len(octave_str)
                elif "," in octave_str:
                    octave -= len(octave_str)

                note_id = (octave + 1) * 12 + CHR_NOTE_DELTA[ord(letter.lower()) - ord("a")]
                lotro_note_id = note_id

                acc = m.group(1)
                if acc:
                    if acc.startswith("_"):
                        accidentals[note_id] = -len(acc)
                    elif acc.startswith("^"):
                        accidentals[note_id] = len(acc)
                    elif acc == "=":
                        accidentals[note_id] = 0

                note_delta = accidentals.get(note_id, info.get_key().get_default_accidental(note_id).delta_note_id)
                lotro_note_id += note_delta
                note_id += note_delta

                if enable_lotro_errors:
                    if lotro_note_id < MIN_PLAYABLE.id:
                        raise LotroParseError("Note is too low", file_name, line_number, m.start())
                    if lotro_note_id > MAX_PLAYABLE.id:
                        raise LotroParseError("Note is too high", file_name, line_number, m.start())

                # Remove stale note-offs
                note_off_events[:] = [
                    (t, n, c, v)
                    for t, n, c, v in note_off_events
                    if not (t <= chord_start_tick and n == note_id)
                ]

                velocity = info.get_dynamics().get_vol(use_lotro_instruments)
                if note_id not in tied_notes:
                    if info.get_ppqn() != ppqn:
                        raise AbcParseError(
                            "Default note length must be the same for all parts",
                            file_name,
                            note_divisor_change_line,
                        )
                    tick = int(chord_start_tick)
                    _, msg = create_note_on_event(note_id, channel, velocity, tick)
                    track_events[track_index].append((tick, msg))

                if m.group(7):
                    tied_notes[note_id] = (line_number << 16) | m.start()
                else:
                    tick_off = int(note_end_tick)
                    # Extend note hold for non-sustained instruments (plucked, percussive) so they ring out
                    prog = info.get_instrument_midi_program()
                    if use_lotro_instruments and is_non_sustained_instrument(prog):
                        hold_ticks = int(
                            NON_SUSTAINED_NOTE_HOLD_SECONDS * cur_tempo * ppqn / 60
                        )
                        tick_off += hold_ticks
                    _, msg_off = create_note_off_event(note_id, channel, velocity, tick_off)
                    track_events[track_index].append((tick_off, msg_off))
                    note_off_events.append((tick_off, note_id, channel, velocity))
                    tied_notes.pop(note_id, None)

                if not in_chord:
                    chord_start_tick = note_end_tick
                i = m.end()

            if tuplet:
                raise AbcParseError("Tuplet not finished by end of line", file_name, line_number, i)
            if in_chord:
                raise AbcParseError("Chord not closed at end of line", file_name, line_number, i)

    if not track_events:
        raise AbcParseError("The file contains no notes", file_name, line_number)

    if tied_notes:
        line_col = next(iter(tied_notes.values()))
        raise AbcParseError(
            "Tied note does not connect to another note",
            file_name,
            line_col >> 16,
            line_col & 0xFFFF,
        )

    # Build MIDI file
    midi_file = mido.MidiFile(type=1, ticks_per_beat=ppqn)
    events_by_track: dict[int, list[tuple[int, object]]] = {}
    for idx, events in track_events.items():
        events_by_track[idx] = sorted(events, key=lambda x: (x[0], str(type(x[1]))))

    # Add tempo and meta to track 0
    tempo_map = info.get_all_parts_tempo_map()
    last_tick = 0
    for tick, bpm in sorted(tempo_map.items()):
        mpqn = bpm_to_mpqn(bpm)
        _, msg = create_tempo_event(mpqn, tick)
        events_by_track.setdefault(0, []).append((tick, msg))
        last_tick = tick
    events_by_track.setdefault(0, []).append((max(last_tick, 1), create_end_of_track_event(max(last_tick, 1))[1]))

    # Add track names and pan
    pan_sorted = list(range(1, track_number + 1))
    pan_sorted.sort(key=lambda i: abc_info.get_part_instrument(i))

    events_by_track[0].append((0, create_track_name_event(abc_info.get_title(), 0)[1]))
    CENTER = 64
    for i in pan_sorted:
        if i in events_by_track:
            part_name = abc_info.get_part_name(i) or f"Part {i}"
            events_by_track[i].insert(0, (0, create_track_name_event(part_name, 0)[1]))
            part_num = abc_info.get_part_number(i)
            # X: values are instrument ids (1, 31, 321, etc.), not sequential. Assignment
            # panel uses those; fallback uses track order (1, 2, 3...). Try both.
            if stereo_mode == "band_layout" and part_pan_map is not None:
                pan_val = (
                    part_pan_map[part_num]
                    if part_num in part_pan_map
                    else part_pan_map.get(i)
                )
            else:
                pan_val = None
            if pan_val is not None:
                if stereo != 100:
                    offset = pan_val - CENTER
                    pan_val = CENTER + int(offset * stereo / 100.0)
                    pan_val = max(0, min(127, pan_val))
            elif stereo_mode == "maestro_user_pan":
                user_pan = abc_info.get_part_user_pan(i)
                if user_pan and user_pan != "auto":
                    try:
                        pan_val = max(0, min(127, int(user_pan)))
                        if stereo != 100:
                            offset = pan_val - CENTER
                            pan_val = CENTER + int(offset * stereo / 100.0)
                            pan_val = max(0, min(127, pan_val))
                    except (ValueError, TypeError):
                        pan_val = get_maestro_pan(
                            abc_info.get_part_instrument(i),
                            abc_info.get_part_name(i),
                            stereo,
                        )
                else:
                    pan_val = get_maestro_pan(
                        abc_info.get_part_instrument(i),
                        abc_info.get_part_name(i),
                        stereo,
                    )
            else:
                pan_val = get_maestro_pan(
                    abc_info.get_part_instrument(i),
                    abc_info.get_part_name(i),
                    stereo,
                )
            _, ch = _get_track_port_and_channel(i)
            events_by_track[i].insert(1, (1, create_pan_event(pan_val, ch, 1)[1]))

    # Time and key signature
    ts = abc_info.get_time_signature()
    ks = abc_info.get_key_signature()
    events_by_track[0].append((0, create_time_signature_event(ts, 0)[1]))
    if is_supported_midi_key_mode(ks.mode):
        events_by_track[0].append((0, create_key_signature_event(ks, 0)[1]))

    # Build tracks with delta times
    for idx in sorted(events_by_track.keys()):
        evs = sorted(events_by_track[idx], key=lambda x: x[0])
        track = mido.MidiTrack()
        if idx > 0:
            port, _ = _get_track_port_and_channel(idx)
            if port > 0:
                track.append(MetaMessage("midi_port", port=port, time=0))
        prev_tick = 0
        for tick, msg in evs:
            delta = tick - prev_tick
            if hasattr(msg, "time"):
                msg.time = delta
            track.append(msg)
            prev_tick = tick
        midi_file.tracks.append(track)

    out = io.BytesIO()
    midi_file.save(file=out)
    return out.getvalue()
