"""
Format ABC filenames from a pattern string with variables.
Mimics Maestro's SetFilenameTemplate for set export.
Inspired by: https://github.com/NikolaiVChr/maestro.
"""

from __future__ import annotations

import re
from pathlib import Path


# Whitespace replacement options (from Maestro ExportFilenameTemplate)
SPACE_REPLACE_CHARS = (" ", "", "_", "-", "RemoveAndCaps")
SPACE_REPLACE_LABELS = (
    "Don't Replace",
    "Remove Spaces",
    "_ (Underscore)",
    "- (Dash)",
    "Remove Spaces and Capitalize first letter",
)

# Variable regex: $VariableName
_VAR_PATTERN = re.compile(r"\$[A-Za-z]+")


def _apply_whitespace_replace(value: str, replace_with: str) -> str:
    """Apply whitespace replacement to a variable value."""
    if replace_with == " ":
        return value
    if replace_with == "":
        return value.replace(" ", "").replace("\t", "")
    if replace_with == "_":
        return re.sub(r"\s+", "_", value)
    if replace_with == "-":
        return re.sub(r"\s+", "-", value)
    if replace_with == "RemoveAndCaps":
        # Remove spaces and capitalize first letter of each word
        words = value.strip().split()
        return "".join(w[:1].upper() + w[1:] if len(w) > 1 else w.upper() for w in words if w)
    return value


def format_filename(
    pattern: str,
    *,
    file_path: str,
    index: int,
    title: str,
    composers: str,
    transcriber: str | None,
    duration_seconds: int | None,
    part_count: int,
    whitespace_replace: str = " ",
    part_count_zero_padded: bool = True,
) -> str:
    """
    Format a filename from the pattern, substituting variables.
    Returns the full filename including .abc extension.
    """
    filename_stem = Path(file_path).stem if file_path else "unknown"
    duration_str = ""
    if duration_seconds is not None:
        m = duration_seconds // 60
        s = duration_seconds % 60
        duration_str = f"{m:02d}_{s:02d}"

    part_fmt = f"{part_count:02d}" if part_count_zero_padded else str(part_count)
    index_fmt = f"{index + 1:03d}"  # 1-based, zero-padded

    variables: dict[str, str] = {
        "$FileName": filename_stem,
        "$SongIndex": index_fmt,
        "$PartCount": part_fmt,
        "$SongComposer": composers or "",
        "$SongTranscriber": transcriber or "",
        "$SongLength": duration_str,
        "$SongTitle": title or "",
    }

    # Find all variable matches, replace in reverse order to avoid index shifts
    matches = list(_VAR_PATTERN.finditer(pattern))
    result = pattern
    for m in reversed(matches):
        var_name = m.group(0)
        value = variables.get(var_name, var_name)
        value = _apply_whitespace_replace(value, whitespace_replace)
        result = result[: m.start()] + value + result[m.end() :]

    # Append .abc if not already present
    if not result.lower().endswith(".abc"):
        result += ".abc"
    return result
