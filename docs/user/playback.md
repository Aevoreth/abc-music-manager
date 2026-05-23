# Playback toolbar

The playback toolbar stays visible at the top of the main window while you use the app.

Playback works by converting the ABC file to MIDI internally, and then plays the constructed midi back using a built-in synthisizer utilizing the lotroinstruments.sf2 soundfont provided by the Maestro Project.

---

## Toolbar controls {#toolbar-controls}

| Control | Action |
|---------|--------|
| **Previous** | Rewind to start; click again within ~1 second for previous track |
| **Play / Resume** | Start or resume playback |
| **Stop** | Stop playback; double-click for MIDI panic |
| **Next** | Next track in playlist |
| **Volume** | Slider 0–100 |
| **Tempo** | Click for popup slider (0.5×–2×) |
| **Parts & Playlist** | Mute/solo parts; reorder or remove queue items |
| **Scrub bar** | Seek within the current song |
| **Stereo slider** | Distance from band (0 = wide L/R, 100 = centered) |
| **Stereo format** | Band layout vs Maestro pan modes |
| **Layout** | Pick active song layout / band layout for stereo |
| **Export playlist** | Create a new setlist from current queue order |

Default volume, tempo, and stereo options come from [ABC Playback settings](settings/abc-playback.md).

---

## Mute and solo {#mute-solo}

Open **Parts & Playlist** to see all parts for the current song. Mute or solo individual parts while listening.

---

## Stereo {#stereo}

**Stereo mode** (in Settings) affects how panning is calculated:

- **Band layout** — uses player positions on the band grid
- **Maestro: user-pan** / **Maestro: Default** — follow pan data from the ABC file

The toolbar **Layout** combo selects which song layout (and band layout) applies when using band-layout mode.

---

## Soundfont {#soundfont}

Playback uses a configurable soundfont (SF2). Leave the path empty in Settings to use automatic lookup or download.

If playback fails silently, check [Troubleshooting → Playback](troubleshooting.md#playback-no-sound).

---

[← User Guide home](index.md) · [Library](library.md) · [Settings → ABC Playback](settings/abc-playback.md)
