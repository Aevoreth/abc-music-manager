"""
Write SongbookData.plugindata (Lua) to configured AccountTarget paths.
REQUIREMENTS §8. Manual action only.
Songbook includes: Music root (with nested exclude rules) + Set Export dir.
Paths in output are relative to \\Music\\.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..db.folder_rule import get_exclude_rules_for_songbook, ExcludeRuleForExport
from ..db.library_query import get_song_metadata_for_file_path
from ..db.instrument import get_instrument_name, resolve_instrument_id
from ..db.account_target import list_account_targets
from ..parsing.abc_parser import parse_abc_file
from ..services.preferences import get_music_root, get_set_export_dir, to_music_relative


def _normalize_path(path_str: str) -> str:
    try:
        return str(Path(path_str).resolve())
    except (OSError, RuntimeError):
        return path_str.strip()


def _path_is_under(path: str, prefix: str) -> bool:
    """True if path is under prefix (normalized)."""
    p = Path(path).resolve()
    pre = Path(prefix).resolve()
    try:
        p.relative_to(pre)
        return True
    except ValueError:
        return False


def _most_specific_exclude_rule(
    path: str, rules: list[ExcludeRuleForExport]
) -> ExcludeRuleForExport | None:
    """Return the exclude rule with the longest path that contains path, or None."""
    containing = [r for r in rules if _path_is_under(path, r.resolved_path)]
    if not containing:
        return None
    return max(containing, key=lambda r: len(r.resolved_path))


def _include_path_in_songbook(
    path_str: str,
    music_root: str,
    set_export_dir: str,
    exclude_rules: list[ExcludeRuleForExport],
) -> bool:
    """
    True if path should be included in SongbookData.
    Include: under set_export_dir; or under music_root and (not under any exclude, or most specific exclude has include_in_export).
    """
    path_str = _normalize_path(path_str)
    music_root = _normalize_path(music_root) if music_root else ""
    set_export_dir = _normalize_path(set_export_dir) if set_export_dir else ""

    if set_export_dir and _path_is_under(path_str, set_export_dir):
        return True
    if not music_root or not _path_is_under(path_str, music_root):
        return False
    rule = _most_specific_exclude_rule(path_str, exclude_rules)
    if rule is None:
        return True
    return rule.include_in_export


def _collect_songbook_abc_paths(
    music_root: str,
    set_export_dir: str,
    exclude_rules: list[ExcludeRuleForExport],
) -> list[Path]:
    """
    Collect all .abc paths for SongbookData: Music root (with nested exclude logic) plus Set Export dir.
    """
    seen: set[str] = set()
    out: list[Path] = []
    music_norm = _normalize_path(music_root) if music_root else ""
    set_export_norm = _normalize_path(set_export_dir) if set_export_dir else ""

    def add(path: Path) -> None:
        try:
            path_str = str(path.resolve())
        except OSError:
            return
        if path_str in seen or not path.is_file():
            return
        seen.add(path_str)
        out.append(path)

    if music_norm:
        music_p = Path(music_norm)
        if music_p.is_dir():
            for f in music_p.rglob("*.abc"):
                if _include_path_in_songbook(str(f.resolve()), music_root, set_export_dir, exclude_rules):
                    add(f)
    if set_export_norm:
        set_p = Path(set_export_norm)
        if set_p.is_dir():
            for f in set_p.rglob("*.abc"):
                add(f)
    return out


def _lua_escape(s: str) -> str:
    """Escape string for Lua double-quoted literal."""
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r")


def _format_duration(seconds: int | None) -> str:
    """Format duration as M:SS for track names."""
    if seconds is None:
        return "0:00"
    m, s = divmod(seconds, 60)
    return f"{m}:{s:02d}"


def build_plugindata_lua(conn) -> str:
    """
    Build Lua table string for SongbookData.plugindata.
    Structure: Directories (unique dir paths) + Songs (Filepath, Filename, Tracks, Transcriber, Artist).
    Paths are relative to \\Music\\, forward slashes, dirs as /path/to/dir/.
    """
    music_root = get_music_root()
    set_export_dir = get_set_export_dir()
    exclude_rules = get_exclude_rules_for_songbook(conn)
    paths = _collect_songbook_abc_paths(music_root, set_export_dir, exclude_rules)

    dirs_set: set[str] = set()
    dirs_set.add("/")
    songs_data: list[dict] = []

    for path in paths:
        path_str = str(path.resolve())
        rel = to_music_relative(path_str)
        if not rel:
            rel = path_str
        rel_posix = rel.replace("\\", "/")
        if not rel_posix.startswith("/"):
            rel_posix = "/" + rel_posix

        meta = get_song_metadata_for_file_path(conn, path_str)
        if meta is None:
            try:
                parsed = parse_abc_file(path)
                title = parsed.title
                composers = parsed.composers
                transcriber = parsed.transcriber
                duration_seconds = parsed.duration_seconds
                parts_list = []
                for p in parsed.parts:
                    iid = resolve_instrument_id(conn, p.made_for) if p.made_for else None
                    parts_list.append({
                        "part_number": p.part_number,
                        "part_name": p.part_name,
                        "instrument_id": iid,
                    })
            except Exception:
                continue
        else:
            title, composers, transcriber, duration_seconds, parts_json = meta
            parts_list = json.loads(parts_json) if parts_json else []

        dir_part = str(Path(rel_posix).parent).replace("\\", "/")
        if not dir_part.startswith("/"):
            dir_part = "/" + dir_part
        if not dir_part.endswith("/"):
            dir_part += "/"
        dirs_set.add(dir_part)

        filename = path.name
        duration_str = _format_duration(duration_seconds)
        artist = (composers or "").strip() or "Unknown"

        tracks: list[tuple[str, str]] = []
        for p in parts_list:
            iid = p.get("instrument_id")
            iname = get_instrument_name(conn, iid) if iid else "Unknown"
            track_id = str(iid) if iid else str(p.get("part_number", len(tracks) + 1))
            track_name = f"{title} ({duration_str}) - {iname}"
            tracks.append((track_id, track_name))

        if not tracks:
            tracks.append(("1", f"{title} ({duration_str}) - Unknown"))

        songs_data.append({
            "filepath": dir_part,
            "filename": filename,
            "tracks": tracks,
            "transcriber": (transcriber or "").strip() or "",
            "artist": artist,
        })

    dirs_sorted = sorted(dirs_set)
    lines = ["return", "{"]
    lines.append('\t["Directories"] =')
    lines.append("\t{")
    for i, d in enumerate(dirs_sorted, 1):
        lines.append(f'\t\t[{i}] = "{_lua_escape(d)}",')
    lines.append("\t},")
    lines.append('\t["Songs"] =')
    lines.append("\t{")
    for si, song in enumerate(songs_data, 1):
        lines.append(f"\t\t[{si}] =")
        lines.append("\t\t{")
        lines.append(f'\t\t\t["Filepath"] = "{_lua_escape(song["filepath"])}",')
        lines.append(f'\t\t\t["Filename"] = "{_lua_escape(song["filename"])}",')
        lines.append('\t\t\t["Tracks"] =')
        lines.append("\t\t\t{")
        for ti, (tid, tname) in enumerate(song["tracks"], 1):
            lines.append(f"\t\t\t\t[{ti}] =")
            lines.append("\t\t\t\t{")
            lines.append(f'\t\t\t\t\t["Id"] ="{_lua_escape(tid)}",')
            lines.append(f'\t\t\t\t\t["Name"] ="{_lua_escape(tname)}"')
            lines.append("\t\t\t\t},")
        lines.append("\t\t\t},")
        lines.append(f'\t\t\t["Transcriber"] = "{_lua_escape(song["transcriber"])}",')
        lines.append(f'\t\t\t["Artist"] = "{_lua_escape(song["artist"])}"')
        lines.append("\t\t},")
    lines.append("\t}")
    lines.append("}")
    return "\n".join(lines)


def write_plugindata_to_path(conn, target_path: str) -> None:
    """Write SongbookData.plugindata (Lua) to the given directory."""
    lua_content = build_plugindata_lua(conn)
    path = Path(target_path)
    path.mkdir(parents=True, exist_ok=True)
    out_file = path / "SongbookData.plugindata"
    out_file.write_text(lua_content, encoding="utf-8")


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
