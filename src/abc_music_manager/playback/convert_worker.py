"""
Standalone ABC-to-MIDI conversion for subprocess. Minimal imports to avoid loading Qt.
"""

from __future__ import annotations

import multiprocessing
from pathlib import Path

from .abc_to_midi import abc_to_midi


def run_conversion(
    file_path: str,
    result_queue: multiprocessing.Queue,
    *,
    stereo: int = 100,
) -> None:
    """
    Run in separate process. Puts (True, midi_bytes) or (False, error_str) in queue.
    stereo: 0-100 from UI (0=close/full L/R, 100=far/centered). Map to abc_to_midi.
    """
    try:
        content = Path(file_path).read_text(encoding="utf-8", errors="replace")
        # abc_to_midi stereo: 100=full spread, 0=all center. UI: 0=full, 100=center
        pan_modifier = 100 - max(0, min(100, stereo))
        midi_bytes = abc_to_midi(content, file_path=file_path, stereo=pan_modifier)
        result_queue.put((True, midi_bytes))
    except Exception as e:
        result_queue.put((False, str(e)))
