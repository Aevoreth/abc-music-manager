"""
Format ABC filenames from a pattern string with variables.
Mimics Maestro's SetFilenameTemplate for set export.
Inspired by: https://github.com/NikolaiVChr/maestro.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any


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


def build_song_variable_map(
    *,
    file_path: str,
    index: int,
    title: str,
    composers: str,
    transcriber: str | None,
    duration_seconds: int | None,
    part_count: int,
    part_count_zero_padded: bool = True,
) -> dict[str, str]:
    """Shared $Song* / $FileName / $PartCount variables for filename and part renaming patterns."""
    filename_stem = Path(file_path).stem if file_path else "unknown"
    duration_str = ""
    if duration_seconds is not None:
        m = duration_seconds // 60
        s = duration_seconds % 60
        duration_str = f"{m:02d}_{s:02d}"

    part_fmt = f"{part_count:02d}" if part_count_zero_padded else str(part_count)
    index_fmt = f"{index + 1:03d}"  # 1-based, zero-padded

    return {
        "$FileName": filename_stem,
        "$SongIndex": index_fmt,
        "$PartCount": part_fmt,
        "$SongComposer": composers or "",
        "$SongTranscriber": transcriber or "",
        "$SongLength": duration_str,
        "$SongTitle": title or "",
    }


def compute_part_numeration(parts: list[dict[str, Any]]) -> dict[int, str]:
    """
    Map part_number -> numeration string: '' if that %%part-name is unique in the song,
    else '1','2',... among parts sharing the same part_name (%%part-name), in parts_json order.
    """
    def name_key(p: dict[str, Any]) -> str:
        v = p.get("part_name")
        if v is None:
            return ""
        return str(v)

    groups: dict[str, list[int]] = {}
    for p in parts:
        pn = int(p.get("part_number") or 0)
        if not pn:
            continue
        k = name_key(p)
        groups.setdefault(k, []).append(pn)

    result: dict[int, str] = {}
    for k, pnums in groups.items():
        if len(pnums) <= 1:
            result[pnums[0]] = ""
        else:
            for idx, pn in enumerate(pnums):
                result[pn] = str(idx + 1)
    return result


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
    variables = build_song_variable_map(
        file_path=file_path,
        index=index,
        title=title,
        composers=composers,
        transcriber=transcriber,
        duration_seconds=duration_seconds,
        part_count=part_count,
        part_count_zero_padded=part_count_zero_padded,
    )

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


def format_part_name(
    pattern: str,
    *,
    file_path: str,
    index: int,
    title: str,
    composers: str,
    transcriber: str | None,
    duration_seconds: int | None,
    part_count: int,
    part_instrument: str,
    part_name: str,
    part_title: str,
    part_number_display: str,
    player_assignment: str,
    numeration: str,
    whitespace_replace: str = " ",
    part_count_zero_padded: bool = True,
) -> str:
    """
    Format the new T: line body from the pattern (no .abc suffix).
    part_name = raw %%part-name; part_title = first T: in the part block.
    """
    variables = build_song_variable_map(
        file_path=file_path,
        index=index,
        title=title,
        composers=composers,
        transcriber=transcriber,
        duration_seconds=duration_seconds,
        part_count=part_count,
        part_count_zero_padded=part_count_zero_padded,
    )
    variables.update(
        {
            "$PartInstrument": part_instrument or "",
            "$PartName": part_name or "",
            "$PartTitle": part_title or "",
            "$PartNumber": part_number_display,
            "$PlayerAssignment": player_assignment or "",
            "$Numeration": numeration or "",
        }
    )

    matches = list(_VAR_PATTERN.finditer(pattern))
    result = pattern
    for m in reversed(matches):
        var_name = m.group(0)
        value = variables.get(var_name, var_name)
        value = _apply_whitespace_replace(value, whitespace_replace)
        result = result[: m.start()] + value + result[m.end() :]

    return result
