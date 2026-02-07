"""
User preferences (e.g. default status for library). Stored as JSON alongside user data.
"""

from __future__ import annotations

import json
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
