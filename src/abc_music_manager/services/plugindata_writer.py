"""
Write SongbookData.plugindata (JSON) to configured AccountTarget paths.
REQUIREMENTS §8. Manual action only.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..db.account_target import list_account_targets
from ..db.library_query import get_primary_file_path_for_song
from ..db import list_library_songs


def build_plugindata_json(conn) -> dict:
    """
    Build JSON structure for LOTRO plugin consumption.
    Uses primary file path per song for library songs.
    """
    songs = list_library_songs(conn, limit=10000)
    entries = []
    for row in songs:
        path = get_primary_file_path_for_song(conn, row.song_id)
        if path:
            entries.append({
                "title": row.title,
                "composers": row.composers,
                "path": path,
            })
    return {"songs": entries, "version": 1}


def write_plugindata_to_path(conn, target_path: str) -> None:
    """Write SongbookData.plugindata to the given directory."""
    data = build_plugindata_json(conn)
    path = Path(target_path)
    path.mkdir(parents=True, exist_ok=True)
    out_file = path / "SongbookData.plugindata"
    out_file.write_text(json.dumps(data, indent=2), encoding="utf-8")


def write_plugindata_all_targets(conn) -> tuple[int, list[str]]:
    """
    Write to all enabled AccountTargets. Returns (success_count, list of errors).
    """
    targets = [t for t in list_account_targets(conn) if t.enabled]
    errors = []
    success = 0
    for t in targets:
        try:
            write_plugindata_to_path(conn, t.plugin_data_path)
            success += 1
        except Exception as e:
            errors.append(f"{t.account_name}: {e}")
    return success, errors
