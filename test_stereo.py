"""Quick stereo test: L/R panned notes. Uses same MIDI path as the app. Use headphones."""
import io
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from abc_music_manager.playback import resolve_soundfont_path

# Use default lookup (MaestroCommon, app data); avoids circular import from preferences
sf_path = resolve_soundfont_path(None)
if not sf_path or not sf_path.is_file():
    print("No soundfont found. Run the app first, go to Settings > Playback, and set/locate the soundfont.")
    sys.exit(1)
print(f"Using soundfont: {sf_path}")

import mido
import tinysoundfont

# Build minimal MIDI: prog 24 (lute), pan left, note; pan right, note
mid = mido.MidiFile(ticks_per_beat=480)
track = mido.MidiTrack()
track.append(mido.Message("program_change", program=24, channel=0, time=0))
track.append(mido.Message("control_change", control=10, value=0, channel=0, time=0))   # Pan left
track.append(mido.Message("note_on", note=60, velocity=100, channel=0, time=0))
track.append(mido.Message("note_off", note=60, velocity=0, channel=0, time=480))    # 1 beat
track.append(mido.Message("control_change", control=10, value=127, channel=0, time=0))  # Pan right
track.append(mido.Message("note_on", note=60, velocity=100, channel=0, time=0))
track.append(mido.Message("note_off", note=60, velocity=0, channel=0, time=480))
track.append(mido.MetaMessage("end_of_track", time=0))
mid.tracks.append(track)

buf = io.BytesIO()
mid.save(file=buf)
midi_bytes = buf.getvalue()

# Same playback path as the app
from abc_music_manager.playback.midi_player import MidiPlayer

player = MidiPlayer(sf_path)
ok, err = player.play(midi_bytes)
if not ok:
    print(f"Play failed: {err}")
    sys.exit(1)
print("Playing: note panned LEFT, then RIGHT. Listen for stereo.")
time.sleep(3.5)
player.stop()
print("Done.")