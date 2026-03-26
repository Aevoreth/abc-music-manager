"""Types for duplicate detection during library scan."""

from __future__ import annotations

from dataclasses import dataclass

from ..parsing.abc_parser import ParsedSong


@dataclass(frozen=True)
class DuplicateCandidate:
    """A new primary-library file that collides with one or more existing songs (same logical identity)."""

    new_path: str
    parsed: ParsedSong
    mtime: str | None
    file_hash: str | None
    is_primary: bool
    is_set_copy: bool
    scan_excluded: bool
    existing_song_ids: list[int]


@dataclass(frozen=True)
class DuplicateDecision:
    """User resolution for one duplicate candidate (matches scanner actions)."""

    new_path: str
    action: str
    existing_song_id: int | None
