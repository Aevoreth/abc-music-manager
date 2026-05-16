"""Locate bundled Set Play worker template and writable deploy directory (dev + PyInstaller)."""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path


def _repo_root() -> Path:
    # .../src/abc_music_manager/services/this_file.py -> repo root is parents[3]
    return Path(__file__).resolve().parents[3]


def worker_template_bundle_path() -> Path | None:
    """Directory containing package.json and wrangler.toml for the relay worker."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        p = Path(sys._MEIPASS) / "workers" / "set-play-relay"
        if p.is_dir():
            return p
        return None
    p = _repo_root() / "workers" / "set-play-relay"
    return p if p.is_dir() else None


def _dir_is_writable(dir_path: Path) -> bool:
    try:
        dir_path.mkdir(parents=True, exist_ok=True)
        probe = dir_path / ".abc_mm_write_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return True
    except OSError:
        return False


def resolve_set_play_deploy_directory() -> Path:
    """
    Development: REPO_ROOT/set-play-relay-deploy (writable).
    Frozen Windows: EXE_DIR/set-play-relay-deploy if writable, else
    LOCALAPPDATA/ABC-Music-Manager/set-play-relay-deploy.
    """
    if not getattr(sys, "frozen", False):
        d = _repo_root() / "set-play-relay-deploy"
        d.mkdir(parents=True, exist_ok=True)
        return d

    if sys.platform == "win32":
        exe_dir = Path(sys.executable).resolve().parent
        candidate = exe_dir / "set-play-relay-deploy"
        if _dir_is_writable(candidate):
            return candidate
        local = os.environ.get("LOCALAPPDATA", "") or str(Path.home() / "AppData" / "Local")
        fallback = Path(local) / "ABC-Music-Manager" / "set-play-relay-deploy"
        if _dir_is_writable(fallback):
            return fallback
        return Path(tempfile.gettempdir()) / "ABC-Music-Manager-set-play-relay-deploy"

    base = Path(sys.executable).resolve().parent
    candidate = base / "set-play-relay-deploy"
    if _dir_is_writable(candidate):
        return candidate
    xdg = os.environ.get("XDG_CACHE_HOME", "") or str(Path.home() / ".cache")
    fallback = Path(xdg) / "abc-music-manager" / "set-play-relay-deploy"
    if _dir_is_writable(fallback):
        return fallback
    return Path(tempfile.gettempdir()) / "abc-music-manager-set-play-relay-deploy"


def sync_worker_template_to_deploy(
    bundle: Path,
    deploy: Path,
    *,
    log_line: object | None = None,
) -> None:
    """Copy worker sources into deploy, skipping node_modules; preserve existing node_modules."""
    def log(msg: str) -> None:
        if log_line is not None and callable(log_line):
            log_line(msg)

    if not bundle.is_dir():
        raise FileNotFoundError(f"Worker bundle not found: {bundle}")
    deploy.mkdir(parents=True, exist_ok=True)
    for item in bundle.iterdir():
        if item.name in ("node_modules", ".wrangler"):
            continue
        dest = deploy / item.name
        try:
            if item.is_file():
                shutil.copy2(item, dest)
            elif item.is_dir():
                shutil.copytree(item, dest, dirs_exist_ok=True)
        except OSError as e:
            log(f"Copy warning ({item.name}): {e}")
            raise
