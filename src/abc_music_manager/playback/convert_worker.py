"""
Standalone ABC-to-MIDI conversion for subprocess. Minimal imports to avoid loading Qt.
"""

from __future__ import annotations

import multiprocessing
import os
from pathlib import Path
from typing import Optional

from .abc_to_midi import abc_to_midi


def run_conversion(
    file_path: str,
    result_queue: multiprocessing.Queue,
    *,
    stereo: int = 100,
    stereo_mode: str = "maestro",
    part_pan_map: Optional[dict[int, int]] = None,
) -> None:
    """
    Run in separate process. Puts (True, midi_bytes) or (False, error_str) in queue.
    stereo: 0-100 from UI (0=close/full L/R, 100=far/centered). Map to abc_to_midi.
    stereo_mode: 'band_layout', 'maestro_user_pan', or 'maestro'. band_layout uses part_pan_map when provided.
    part_pan_map: part_number (1-based) -> pan (0-127) for band_layout mode.
    """
    try:
        content = Path(file_path).read_text(encoding="utf-8", errors="replace")
        # abc_to_midi stereo: 100=full spread, 0=all center. UI: 0=full, 100=center
        pan_modifier = 100 - max(0, min(100, stereo))
        if __debug__ and os.environ.get("ABC_PAN_DEBUG") == "1":
            import sys
            print(
                f"[pan] convert: UI_stereo={stereo} -> pan_modifier={pan_modifier} (100=full spread, 0=all center)",
                file=sys.stderr,
                flush=True,
            )
        midi_bytes = abc_to_midi(
            content,
            file_path=file_path,
            stereo=pan_modifier,
            stereo_mode=stereo_mode,
            part_pan_map=part_pan_map,
        )
        result_queue.put((True, midi_bytes))
    except Exception as e:
        result_queue.put((False, str(e)))
