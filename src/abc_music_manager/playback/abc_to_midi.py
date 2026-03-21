"""
Convert ABC content to MIDI, with LOTRO instrument mapping from %%part-name/%%made-for.
Uses native maestro_abc engine (handles complex time signatures).
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from .maestro_abc.abc_to_midi import abc_to_midi as _maestro_abc_to_midi


def abc_to_midi(
    abc_content: str,
    file_path: Optional[str | Path] = None,
    *,
    stereo: int = 100,
    stereo_mode: str = "maestro",
    part_pan_map: Optional[dict[int, int]] = None,
) -> bytes:
    """
    Convert ABC content to MIDI bytes.
    Uses native maestro_abc engine. Applies LOTRO instrument mapping from %%part-name and %%made-for per part.
    stereo: 0-100, pan modifier (100=full spread, 0=centered).
    stereo_mode: 'maestro' or 'band_layout'. band_layout uses part_pan_map when provided.
    part_pan_map: part_number (1-based) -> pan (0-127) for band_layout mode.
    Returns raw MIDI file bytes.
    """
    return _maestro_abc_to_midi(
        abc_content,
        file_path,
        stereo=stereo,
        stereo_mode=stereo_mode,
        part_pan_map=part_pan_map,
    )
