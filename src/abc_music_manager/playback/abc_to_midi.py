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
) -> bytes:
    """
    Convert ABC content to MIDI bytes.
    Uses native maestro_abc engine. Applies LOTRO instrument mapping from %%part-name and %%made-for per part.
    Returns raw MIDI file bytes.
    """
    return _maestro_abc_to_midi(abc_content, file_path)
