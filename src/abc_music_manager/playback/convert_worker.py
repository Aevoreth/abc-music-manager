"""
Standalone ABC-to-MIDI conversion for subprocess. Minimal imports to avoid loading Qt/FluidSynth.
"""

from __future__ import annotations

import multiprocessing
from pathlib import Path

from .abc_to_midi import abc_to_midi


def run_conversion(file_path: str, result_queue: multiprocessing.Queue) -> None:
    """
    Run in separate process. Puts (True, midi_bytes) or (False, error_str) in queue.
    Called by multiprocessing.Process.
    """
    try:
        content = Path(file_path).read_text(encoding="utf-8", errors="replace")
        midi_bytes = abc_to_midi(content, file_path=file_path)
        result_queue.put((True, midi_bytes))
    except Exception as e:
        result_queue.put((False, str(e)))
