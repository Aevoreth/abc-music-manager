"""
User preferences (e.g. default status for library). Stored as JSON alongside user data.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from ..db.schema import get_db_path


def _preferences_path() -> Path:
    return get_db_path().parent / "preferences.json"


def load_preferences() -> dict[str, Any]:
    """Load preferences from disk. Returns dict; missing file or invalid JSON => {}."""
    path = _preferences_path()
    if not path.exists():
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_preferences(prefs: dict[str, Any]) -> None:
    """Save preferences to disk."""
    path = _preferences_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(prefs, f, indent=2)


def get_default_status_id() -> int | None:
    """Default status id for library (songs with no status show this). None = no default."""
    prefs = load_preferences()
    v = prefs.get("default_status_id")
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def set_default_status_id(status_id: int | None) -> None:
    """Set default status id in preferences."""
    prefs = load_preferences()
    if status_id is None:
        prefs.pop("default_status_id", None)
    else:
        prefs["default_status_id"] = status_id
    save_preferences(prefs)


def get_base_font_size() -> int:
    """Base font size in points. 0 = use system default; 8–16 = point size."""
    prefs = load_preferences()
    v = prefs.get("base_font_size")
    if v is None:
        return 0
    try:
        n = int(v)
        if n == 0:
            return 0
        return max(8, min(16, n))
    except (TypeError, ValueError):
        return 0


def set_base_font_size(size: int) -> None:
    """Set base font size in points. 0 = system default, 8–16 = point size."""
    prefs = load_preferences()
    n = int(size)
    prefs["base_font_size"] = 0 if n <= 0 else max(8, min(16, n))
    save_preferences(prefs)


def get_window_geometry() -> dict[str, Any] | str | None:
    """
    Saved main window geometry. Returns dict with x, y, width, height, maximized (human-readable),
    or legacy base64 str. None if not set.
    """
    prefs = load_preferences()
    return prefs.get("window_geometry")


def set_window_geometry(geometry: dict[str, Any]) -> None:
    """Save main window geometry as human-readable dict: x, y, width, height, maximized."""
    prefs = load_preferences()
    prefs["window_geometry"] = geometry
    save_preferences(prefs)


def get_splitter_state() -> list[int] | str | None:
    """
    Saved nav/main splitter state. Returns list of sizes (human-readable),
    or legacy base64 str. None if not set.
    """
    prefs = load_preferences()
    return prefs.get("splitter_state")


def set_splitter_state(sizes: list[int]) -> None:
    """Save nav/main splitter state as human-readable list of section sizes in pixels."""
    prefs = load_preferences()
    prefs["splitter_state"] = sizes
    save_preferences(prefs)


def get_bands_splitter_state() -> list[int] | None:
    """Saved bands tab splitter state (band list | editor). Returns list of sizes or None."""
    prefs = load_preferences()
    v = prefs.get("bands_splitter_state")
    if isinstance(v, list) and len(v) >= 2:
        try:
            return [int(v[0]), int(v[1])]
        except (TypeError, ValueError):
            pass
    return None


def set_bands_splitter_state(sizes: list[int]) -> None:
    """Save bands tab splitter state as list of section sizes in pixels."""
    prefs = load_preferences()
    prefs["bands_splitter_state"] = sizes
    save_preferences(prefs)


def get_setlists_splitter_state() -> list[int] | None:
    """Saved setlists tab splitter (setlist list | editor)."""
    prefs = load_preferences()
    v = prefs.get("setlists_splitter_state")
    if isinstance(v, list) and len(v) >= 2:
        try:
            return [int(v[0]), int(v[1])]
        except (TypeError, ValueError):
            pass
    return None


def set_setlists_splitter_state(sizes: list[int]) -> None:
    prefs = load_preferences()
    prefs["setlists_splitter_state"] = sizes
    save_preferences(prefs)


def get_setlists_editor_splitter_state() -> list[int] | None:
    """Saved setlists editor splitter (options+songs | band layout)."""
    prefs = load_preferences()
    v = prefs.get("setlists_editor_splitter_state")
    if isinstance(v, list) and len(v) >= 2:
        try:
            return [int(v[0]), int(v[1])]
        except (TypeError, ValueError):
            pass
    return None


def set_setlists_editor_splitter_state(sizes: list[int]) -> None:
    prefs = load_preferences()
    prefs["setlists_editor_splitter_state"] = sizes
    save_preferences(prefs)


def get_setlists_top_split_state() -> list[int] | None:
    """Saved setlists top split (meta | songs)."""
    prefs = load_preferences()
    v = prefs.get("setlists_top_split_state")
    if isinstance(v, list) and len(v) >= 2:
        try:
            return [int(v[0]), int(v[1])]
        except (TypeError, ValueError):
            pass
    return None


def set_setlists_top_split_state(sizes: list[int]) -> None:
    prefs = load_preferences()
    prefs["setlists_top_split_state"] = sizes
    save_preferences(prefs)


def get_setlists_songs_table_header_state() -> list[int] | None:
    """Saved setlists songs table column widths."""
    prefs = load_preferences()
    v = prefs.get("setlists_songs_table_header_state")
    if isinstance(v, list):
        try:
            return [int(x) for x in v]
        except (TypeError, ValueError):
            pass
    return None


def set_setlists_songs_table_header_state(sizes: list[int]) -> None:
    prefs = load_preferences()
    prefs["setlists_songs_table_header_state"] = sizes
    save_preferences(prefs)


def get_parts_playlist_popup_geometry() -> dict[str, int] | None:
    """Saved Parts/Playlist popup size: {width, height}. None if not set."""
    prefs = load_preferences()
    v = prefs.get("parts_playlist_popup_geometry")
    if isinstance(v, dict) and "width" in v and "height" in v:
        try:
            w, h = int(v["width"]), int(v["height"])
            if w >= 400 and h >= 300:
                return {"width": w, "height": h}
        except (TypeError, ValueError):
            pass
    return None


def set_parts_playlist_popup_geometry(width: int, height: int) -> None:
    """Save Parts/Playlist popup size."""
    prefs = load_preferences()
    prefs["parts_playlist_popup_geometry"] = {"width": width, "height": height}
    save_preferences(prefs)


def get_parts_playlist_splitter_state() -> list[int] | None:
    """Saved Parts/Playlist splitter sizes. None if not set."""
    prefs = load_preferences()
    v = prefs.get("parts_playlist_splitter_state")
    if isinstance(v, list) and len(v) >= 2:
        try:
            return [int(x) for x in v]
        except (TypeError, ValueError):
            pass
    return None


def set_parts_playlist_splitter_state(sizes: list[int]) -> None:
    """Save Parts/Playlist splitter sizes."""
    prefs = load_preferences()
    prefs["parts_playlist_splitter_state"] = sizes
    save_preferences(prefs)


def get_playback_playlist_table_columns() -> list[int] | None:
    """Saved playback playlist table column widths. None if not set."""
    prefs = load_preferences()
    v = prefs.get("playback_playlist_table_columns")
    if isinstance(v, list) and len(v) >= 5:
        try:
            return [int(x) for x in v]
        except (TypeError, ValueError):
            pass
    return None


def set_playback_playlist_table_columns(sizes: list[int]) -> None:
    """Save playback playlist table column widths."""
    prefs = load_preferences()
    prefs["playback_playlist_table_columns"] = sizes
    save_preferences(prefs)


def get_setlists_folder_expanded_state() -> list[int]:
    """Folder ids that are expanded. Returns empty list if not set."""
    prefs = load_preferences()
    v = prefs.get("setlists_folder_expanded_state")
    if isinstance(v, list):
        try:
            return [int(x) for x in v]
        except (TypeError, ValueError):
            pass
    return []


def set_setlists_folder_expanded_state(folder_ids: list[int]) -> None:
    """Save folder ids that are expanded."""
    prefs = load_preferences()
    prefs["setlists_folder_expanded_state"] = folder_ids
    save_preferences(prefs)


def get_library_table_header_state() -> dict[str, Any] | str | None:
    """
    Saved library table header state. Returns dict with section_sizes, sort_column, sort_order
    (human-readable), or legacy base64 str. None if not set.
    """
    prefs = load_preferences()
    return prefs.get("library_table_header_state")


def set_library_table_header_state(state: dict[str, Any]) -> None:
    """Save library table header state as human-readable dict: section_sizes, sort_column, sort_order."""
    prefs = load_preferences()
    prefs["library_table_header_state"] = state
    save_preferences(prefs)


# --- Default library filters ---
# Stored under "default_filters" key. Keys: in_set, rating_from, rating_to, duration_min_none,
# duration_max_none, duration_min_sec, duration_max_sec, last_played_mode, last_played_from_seconds_ago,
# last_played_to_seconds_ago, last_played_from_iso, last_played_to_iso, parts_min, parts_max, status_ids.

_BUILTIN_DEFAULT_FILTERS: dict[str, Any] = {
    "in_set": None,
    "rating_from": 0,
    "rating_to": 5,
    "duration_min_none": True,
    "duration_max_none": True,
    "duration_min_sec": 0,
    "duration_max_sec": 1200,  # 20 minutes
    "last_played_mode": "time",
    "last_played_from_seconds_ago": 0,
    "last_played_to_seconds_ago": None,
    "last_played_from_iso": None,
    "last_played_to_iso": None,
    "parts_min": 1,
    "parts_max": 24,
    "status_ids": [],
}


def get_default_filters() -> dict[str, Any]:
    """Return default library filter values. Merges stored prefs with built-in defaults."""
    prefs = load_preferences()
    stored = prefs.get("default_filters")
    if not isinstance(stored, dict):
        return _BUILTIN_DEFAULT_FILTERS.copy()
    out = _BUILTIN_DEFAULT_FILTERS.copy()
    for k in out:
        if k in stored:
            out[k] = stored[k]
    return out


def set_default_filters(filters: dict[str, Any]) -> None:
    """Save default library filter values."""
    prefs = load_preferences()
    valid = {k: v for k, v in filters.items() if k in _BUILTIN_DEFAULT_FILTERS}
    prefs["default_filters"] = valid
    save_preferences(prefs)


# --- Lord of the Rings Online root directory ---
# Single root containing \Music\ (library) and \PluginData\<account>\AllServers\ (SongbookData.plugindata).

LOTRO_FOLDER_NAME = "The Lord of the Rings Online"


def _get_documents_library_path() -> str:
    """
    Return the system's Documents library path. On Windows uses the Known Folders API
    (FOLDERID_Documents) so the actual Documents library location is used, not a guessed path.
    Returns empty string on failure or non-Windows.
    """
    if sys.platform != "win32":
        try:
            docs = Path.home() / "Documents"
            if docs.exists() and docs.is_dir():
                return str(docs.resolve())
        except (OSError, RuntimeError):
            pass
        return ""

    try:
        import ctypes
        from ctypes import wintypes

        class GUID(ctypes.Structure):
            _fields_ = [
                ("Data1", wintypes.DWORD),
                ("Data2", wintypes.WORD),
                ("Data3", wintypes.WORD),
                ("Data4", wintypes.BYTE * 8),
            ]

        # FOLDERID_Documents
        FOLDERID_DOCUMENTS = GUID(
            0xFDD39AD0,
            0x238F,
            0x46AF,
            (ctypes.c_byte * 8)(0xAD, 0xB4, 0x6C, 0x85, 0x48, 0x03, 0x69, 0xC7),
        )
        shell32 = ctypes.windll.shell32  # type: ignore[attr-defined]
        path_buf = ctypes.c_void_p()
        hr = shell32.SHGetKnownFolderPath(
            ctypes.byref(FOLDERID_DOCUMENTS),
            0,
            None,
            ctypes.byref(path_buf),
        )
        if hr != 0 or not path_buf.value:
            raise OSError("SHGetKnownFolderPath failed")
        path = ctypes.wstring_at(path_buf.value)
        ctypes.windll.ole32.CoTaskMemFree(path_buf.value)  # type: ignore[attr-defined]
        if path and Path(path).exists():
            return path
    except Exception:
        pass
    # Fallback: standard Documents under user profile (e.g. if Known Folders API fails)
    try:
        docs = Path.home() / "Documents"
        if docs.exists() and docs.is_dir():
            return str(docs.resolve())
    except (OSError, RuntimeError):
        pass
    return ""


def get_default_lotro_root() -> str:
    """
    Return the default Lord of the Rings Online directory path if it exists.
    Uses the system's Documents library (on Windows, the actual Documents known folder),
    then looks for the LOTRO folder within it. Tries "The Lord of the Rings Online"
    then "Lord of the Rings Online". Returns empty string if no default location is found.
    """
    docs = _get_documents_library_path()
    if not docs:
        return ""
    docs_path = Path(docs)
    for folder_name in (LOTRO_FOLDER_NAME, "Lord of the Rings Online"):
        lotro = docs_path / folder_name
        try:
            if lotro.exists() and lotro.is_dir():
                return str(lotro.resolve())
        except (OSError, RuntimeError):
            pass
    return ""


def get_lotro_root() -> str:
    """Current Lord of the Rings Online root directory (contains Music and PluginData). Empty if not set."""
    prefs = load_preferences()
    path = (prefs.get("lotro_root") or "").strip()
    if path:
        return path
    default = get_default_lotro_root()
    if default:
        return default
    return ""


def set_lotro_root(path: str) -> None:
    """Set the Lord of the Rings Online root directory."""
    prefs = load_preferences()
    prefs["lotro_root"] = (path or "").strip()
    save_preferences(prefs)


def ensure_default_lotro_root() -> None:
    """
    On first load, if no LOTRO root is saved in settings, try to locate the default
    (Documents library / The Lord of the Rings Online) and save it to preferences.
    Idempotent: only writes when lotro_root is currently unset and default exists.
    Call from app startup and when Folder Rules tab is shown with empty field.
    """
    prefs = load_preferences()
    if (prefs.get("lotro_root") or "").strip():
        return
    default = get_default_lotro_root()
    if default:
        set_lotro_root(default)


def get_music_root() -> str:
    """Return the root Music folder path (lotro_root/Music). Empty if lotro_root not set."""
    lotro = get_lotro_root()
    if not lotro:
        return ""
    try:
        music = Path(lotro) / "Music"
        return str(music.resolve())
    except (OSError, RuntimeError):
        return ""


def get_set_export_dir_stored() -> str:
    """
    Return the Set Export directory as stored (relative to Music when applicable).
    Use for display in the UI so the user sees the relative path.
    """
    prefs = load_preferences()
    return (prefs.get("set_export_dir") or "").strip()


def get_set_export_dir() -> str:
    """
    Single Set Export directory (resolved to absolute path). Use for scanning and file ops.
    When stored value is relative to Music, resolves against get_music_root().
    """
    stored = get_set_export_dir_stored()
    if not stored:
        return ""
    try:
        if not Path(stored).is_absolute():
            music = get_music_root()
            if music:
                return str((Path(music) / stored).resolve())
    except (OSError, RuntimeError):
        pass
    return stored


def set_set_export_dir(path: str) -> None:
    """
    Set the single Set Export directory. If path is under the Music folder,
    store as relative to Music; otherwise store as absolute.
    """
    path = (path or "").strip()
    prefs = load_preferences()
    if not path:
        prefs["set_export_dir"] = ""
        save_preferences(prefs)
        return
    try:
        music = get_music_root()
        if music:
            full = Path(path).resolve()
            music_p = Path(music).resolve()
            try:
                rel = full.relative_to(music_p)
                prefs["set_export_dir"] = rel.as_posix()
                save_preferences(prefs)
                return
            except ValueError:
                pass
    except (OSError, RuntimeError):
        pass
    prefs["set_export_dir"] = path
    save_preferences(prefs)


def get_set_export_prefs() -> dict[str, Any]:
    """Load set export preferences. Returns dict with defaults for missing keys."""
    prefs = load_preferences()
    se = prefs.get("set_export") or {}
    defaults = {
        "output_directory": "",
        "rename_abc_files": True,
        "export_as_folder": True,
        "export_as_zip": False,
        "filename_pattern": "$SongIndex_$FileName",
        "whitespace_replace": " ",
        "export_csv_part_sheet": False,
        "include_composer_in_csv": True,
        "csv_use_visible_columns": True,
        "csv_columns_enabled": {
            "Title": True,
            "Part Count": True,
            "Duration": True,
            "Composers": True,
            "Transcriber": True,
        },
        "csv_part_columns": "part",
    }
    result = dict(defaults)
    for k, v in se.items():
        if k in result:
            result[k] = v
    return result


def save_set_export_prefs(prefs: dict[str, Any]) -> None:
    """Save set export preferences."""
    all_prefs = load_preferences()
    all_prefs["set_export"] = prefs
    save_preferences(all_prefs)


def to_music_relative(path: str) -> str:
    """
    If path is under the Music folder, return it as relative to Music (e.g. for exclude rules).
    Otherwise return path unchanged (absolute). Uses forward slashes for relative form.
    """
    path = (path or "").strip()
    if not path:
        return ""
    try:
        music = get_music_root()
        if not music:
            return path
        full = Path(path).resolve()
        music_p = Path(music).resolve()
        return full.relative_to(music_p).as_posix()
    except (ValueError, OSError, RuntimeError):
        return path


# --- Playback preferences ---


def get_playback_soundfont_path() -> str:
    """User-configured soundfont path. Empty = use default lookup."""
    prefs = load_preferences()
    return (prefs.get("playback_soundfont_path") or "").strip()


def set_playback_soundfont_path(path: str) -> None:
    """Set soundfont path. Empty = use default lookup."""
    prefs = load_preferences()
    prefs["playback_soundfont_path"] = (path or "").strip()
    save_preferences(prefs)


def get_playback_volume() -> float:
    """Volume 0-100. Default 70."""
    prefs = load_preferences()
    v = prefs.get("playback_volume")
    if v is None:
        return 70.0
    try:
        return max(0.0, min(100.0, float(v)))
    except (TypeError, ValueError):
        return 70.0


def set_playback_volume(value: float) -> None:
    """Set volume 0-100."""
    prefs = load_preferences()
    prefs["playback_volume"] = max(0.0, min(100.0, float(value)))
    save_preferences(prefs)


def get_playback_tempo() -> float:
    """Tempo factor 0.5-2.0. Default 1.0."""
    prefs = load_preferences()
    v = prefs.get("playback_tempo")
    if v is None:
        return 1.0
    try:
        return max(0.5, min(2.0, float(v)))
    except (TypeError, ValueError):
        return 1.0


def set_playback_tempo(value: float) -> None:
    """Set tempo factor 0.5-2.0."""
    prefs = load_preferences()
    prefs["playback_tempo"] = max(0.5, min(2.0, float(value)))
    save_preferences(prefs)


_STEREO_MODES = ("band_layout", "maestro_user_pan", "maestro")


def get_playback_stereo_mode() -> str:
    """'band_layout', 'maestro_user_pan', or 'maestro'. Default maestro."""
    prefs = load_preferences()
    v = prefs.get("playback_stereo_mode") or "maestro"
    return v if v in _STEREO_MODES else "maestro"


def set_playback_stereo_mode(mode: str) -> None:
    """Set stereo mode: band_layout, maestro_user_pan, or maestro."""
    prefs = load_preferences()
    prefs["playback_stereo_mode"] = mode if mode in _STEREO_MODES else "maestro"
    save_preferences(prefs)


def get_playback_stereo_slider() -> int:
    """Stereo width 0-100. Default 0 = full L/R spread (stereo). 100 = all center (mono)."""
    prefs = load_preferences()
    v = prefs.get("playback_stereo_slider")
    if v is None:
        return 0  # Full stereo by default; was 100 which collapsed all pans to center
    try:
        return max(0, min(100, int(v)))
    except (TypeError, ValueError):
        return 0


def set_playback_stereo_slider(value: int) -> None:
    """Set stereo width 0-100."""
    prefs = load_preferences()
    prefs["playback_stereo_slider"] = max(0, min(100, int(value)))
    save_preferences(prefs)


def resolve_music_path(relative_or_absolute: str) -> str:
    """
    If path is relative, resolve against the Music folder and return absolute path.
    If path is absolute, return as-is. For use when displaying or browsing.
    """
    path = (relative_or_absolute or "").strip()
    if not path:
        return ""
    try:
        p = Path(path)
        if p.is_absolute():
            return path
        music = get_music_root()
        if music:
            return str((Path(music) / p).resolve())
    except (OSError, RuntimeError):
        pass
    return path
