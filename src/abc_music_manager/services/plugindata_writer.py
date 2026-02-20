"""
Write SongbookData.plugindata (JSON) to configured AccountTarget paths.
REQUIREMENTS §8. Manual action only.
Songbook includes: Music root (with nested exclude rules) + Set Export dir.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..db.folder_rule import get_exclude_rules_for_songbook, ExcludeRuleForExport
from ..db.library_query import get_title_composers_for_file_path
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


def build_plugindata_json(conn) -> dict:
    """
    Build JSON structure for LOTRO plugin consumption.
    Includes all files for SongbookData: Music root (respecting nested exclude/include_in_export)
    plus Set Export directory. Paths in output are relative to Music when under Music.
    """
    music_root = get_music_root()
    set_export_dir = get_set_export_dir()
    exclude_rules = get_exclude_rules_for_songbook(conn)
    paths = _collect_songbook_abc_paths(music_root, set_export_dir, exclude_rules)

    entries = []
    for path in paths:
        path_str = str(path.resolve())
        meta = get_title_composers_for_file_path(conn, path_str)
        if meta is None:
            try:
                parsed = parse_abc_file(path)
                title = parsed.title
                composers = parsed.composers
            except Exception:
                continue
        else:
            title, composers = meta
        path_for_plugin = to_music_relative(path_str)
        if not path_for_plugin:
            path_for_plugin = path_str
        entries.append({
            "title": title,
            "composers": composers,
            "path": path_for_plugin,
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
