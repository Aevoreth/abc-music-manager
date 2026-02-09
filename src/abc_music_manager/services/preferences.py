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


def get_window_geometry() -> str | None:
    """Saved main window geometry (base64). None if not set or invalid."""
    prefs = load_preferences()
    return prefs.get("window_geometry")


def set_window_geometry(geometry_b64: str) -> None:
    """Save main window geometry (base64 from QMainWindow.saveGeometry())."""
    prefs = load_preferences()
    prefs["window_geometry"] = geometry_b64
    save_preferences(prefs)


def get_splitter_state() -> str | None:
    """Saved nav/main splitter state (base64 from QSplitter.saveState()). None if not set."""
    prefs = load_preferences()
    return prefs.get("splitter_state")


def set_splitter_state(state_b64: str) -> None:
    """Save nav/main splitter state (base64 from QSplitter.saveState())."""
    prefs = load_preferences()
    prefs["splitter_state"] = state_b64
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
