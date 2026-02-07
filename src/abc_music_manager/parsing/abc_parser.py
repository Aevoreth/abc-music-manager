"""
ABC file parser: Maestro tags, fallbacks, parts. No musical note bodies stored.
FILE_FORMATS.md, REQUIREMENTS §2, DECISIONS 007, 024.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# Maestro tag pattern: %%tag-name (case-sensitive), optional space, value (trimmed)
# Tag names are case-sensitive (FILE_FORMATS / DECISIONS 024); no re.IGNORECASE
_MAESTRO_TAG = re.compile(r"^%%([a-z]+(?:-[a-z]+)*)\s*(.*)$")


@dataclass
class PartInfo:
    """One part from ABC: part number, optional name, optional made-for (raw string for instrument resolution)."""
    part_number: int
    part_name: Optional[str] = None
    made_for: Optional[str] = None  # caller resolves to instrument_id


@dataclass
class ParsedSong:
    """Parsed song metadata and parts only; no note bodies."""
    title: str
    composers: str  # single string, no comma split
    duration_seconds: Optional[int] = None
    transcriber: Optional[str] = None
    export_timestamp: Optional[str] = None
    parts: list[PartInfo] = field(default_factory=list)


def _parse_mm_ss(value: str) -> Optional[int]:
    """Convert mm:ss to total seconds. Returns None if unparseable."""
    value = value.strip()
    if not value:
        return None
    parts = value.split(":")
    if len(parts) == 2:
        try:
            m, s = int(parts[0].strip()), int(parts[1].strip())
            if m >= 0 and 0 <= s < 60:
                return m * 60 + s
        except ValueError:
            pass
    return None


def _get_maestro_value(tags: dict[str, str], key: str) -> Optional[str]:
    """Get tag value; keys are lowercase with hyphens, e.g. song-title."""
    v = tags.get(key)
    return v.strip() if v else None


def _parse_headers(content: str) -> tuple[dict[str, str], str, str, str]:
    """
    Parse Maestro tags and first T:, C:, Z: from the file (any order).
    Returns (maestro_tags_dict, first_T, first_C, first_Z).
    """
    maestro: dict[str, str] = {}
    first_t: Optional[str] = None
    first_c: Optional[str] = None
    first_z: Optional[str] = None

    for line in content.splitlines():
        line_stripped = line.strip()
        if not line_stripped:
            continue
        m = _MAESTRO_TAG.match(line_stripped)
        if m:
            tag_name = m.group(1).strip().lower()
            tag_value = m.group(2).strip() if m.group(2) is not None else ""
            maestro[tag_name] = tag_value
            continue
        # ABC header: T:, C:, Z: (only first of each for fallbacks)
        if line_stripped.startswith("T:") and first_t is None:
            first_t = line_stripped[2:].strip()
        elif line_stripped.startswith("C:") and first_c is None:
            first_c = line_stripped[2:].strip()
        elif line_stripped.startswith("Z:") and first_z is None:
            first_z = line_stripped[2:].strip()

    return maestro, first_t or "", first_c or "", first_z or ""


def _parse_parts(content: str) -> list[PartInfo]:
    """
    Find all X: lines; each starts a part block until next X: or EOF.
    In each block: X: -> part_number, %%part-name -> part_name, %%made-for -> made_for.
    """
    parts: list[PartInfo] = []
    x_pattern = re.compile(r"^X:\s*(\d+)", re.IGNORECASE)
    lines = content.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        m = x_pattern.match(line.strip())
        if m:
            part_num = int(m.group(1))
            part_name: Optional[str] = None
            made_for: Optional[str] = None
            i += 1
            while i < len(lines):
                rest = lines[i]
                stripped = rest.strip()
                if x_pattern.match(stripped):
                    break
                tag = _MAESTRO_TAG.match(stripped)
                if tag:
                    name = tag.group(1).strip().lower()
                    val = (tag.group(2) or "").strip()
                    if name == "part-name":
                        part_name = val or None
                    elif name == "made-for":
                        made_for = val or None
                i += 1
            parts.append(PartInfo(part_number=part_num, part_name=part_name, made_for=made_for))
            continue
        i += 1
    return parts


def parse_abc_content(
    content: str,
    *,
    filename: Optional[str] = None,
) -> ParsedSong:
    """
    Parse ABC content (metadata and parts only; no note bodies).
    filename is used only as fallback for title when no tag/T: present.
    """
    maestro, first_t, first_c, first_z = _parse_headers(content)
    parts = _parse_parts(content)

    # Title: %%song-title -> T: -> filename
    title = _get_maestro_value(maestro, "song-title")
    if not title:
        title = first_t or (filename or "Unknown")
    title = title.strip() or "Unknown"

    # Composer: %%song-composer -> C: -> "Unknown" (single string, no comma split)
    composers = _get_maestro_value(maestro, "song-composer")
    if not composers:
        composers = first_c or "Unknown"
    composers = composers.strip() or "Unknown"

    # Transcriber: %%song-transcriber -> Z: -> blank/unknown
    transcriber = _get_maestro_value(maestro, "song-transcriber")
    if transcriber is None or transcriber == "":
        transcriber = first_z or None
    if transcriber is not None:
        transcriber = transcriber.strip() or None

    # Duration: %%song-duration (mm:ss) -> unknown if missing
    duration_seconds: Optional[int] = None
    dur_str = _get_maestro_value(maestro, "song-duration")
    if dur_str:
        duration_seconds = _parse_mm_ss(dur_str)

    # Export timestamp
    export_timestamp = _get_maestro_value(maestro, "export-timestamp")

    return ParsedSong(
        title=title,
        composers=composers,
        duration_seconds=duration_seconds,
        transcriber=transcriber,
        export_timestamp=export_timestamp,
        parts=parts,
    )


def parse_abc_file(file_path: str | Path) -> ParsedSong:
    """Read file and parse; uses file path for title fallback."""
    path = Path(file_path)
    content = path.read_text(encoding="utf-8", errors="replace")
    return parse_abc_content(content, filename=path.name)
