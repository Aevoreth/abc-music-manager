"""
Resolve LotroInstruments.sf2 path: user config, MaestroCommon, download.
Based on Maestro SoundFontDownloader.
Source: https://github.com/NikolaiVChr/maestro. SF2 from NikolaiVChr/mver.
"""

from __future__ import annotations

import hashlib
import os
import urllib.request
from pathlib import Path
from typing import Callable, Optional

# From Maestro SoundFontDownloader
SF2_URL = "https://github.com/NikolaiVChr/mver/releases/download/v4.5.24/LotroInstruments.sf2"
EXPECTED_SHA256 = "3b2ef0407e3219f92a379dc8c60ec4aa1d91e532e9646a59f01b1c79e54678af"
SF2_FILENAME_VERSIONED = f"LotroInstruments_{EXPECTED_SHA256[:8]}.sf2"
SF2_FILENAME_LEGACY = "LotroInstruments.sf2"


def _get_maestro_common_dir() -> Path:
    """MaestroCommon directory per platform."""
    os_name = os.name
    home = Path.home()
    if os_name == "nt":  # Windows
        local = os.environ.get("LOCALAPPDATA")
        if not local:
            local = str(home / "AppData" / "Local")
        return Path(local) / "MaestroCommon"
    if os_name == "posix":
        # macOS vs Linux
        if (home / "Library").exists():
            return home / "Library" / "Application Support" / "MaestroCommon"
        xdg = os.environ.get("XDG_DATA_HOME")
        if xdg:
            return Path(xdg) / "maestro-common"
        return home / ".local" / "share" / "maestro-common"
    return home / ".maestro_common"


def resolve_soundfont_path(user_path: Optional[str] = None) -> Optional[Path]:
    """
    Resolve path to LotroInstruments soundfont.
    Lookup order: user_path, MaestroCommon (versioned + legacy), app data dir.
    Returns Path if found, None otherwise.
    """
    # 1. User-configured path
    if user_path and user_path.strip():
        p = Path(user_path.strip())
        if p.is_file():
            return p.resolve()
        if p.is_dir():
            for name in (SF2_FILENAME_VERSIONED, SF2_FILENAME_LEGACY):
                candidate = p / name
                if candidate.is_file():
                    return candidate.resolve()

    # 2. MaestroCommon
    common = _get_maestro_common_dir()
    for name in (SF2_FILENAME_VERSIONED, SF2_FILENAME_LEGACY):
        candidate = common / name
        if candidate.is_file():
            return candidate.resolve()

    # 3. ABC Music Manager data dir
    from ..db.schema import get_db_path
    app_dir = get_db_path().parent
    for name in (SF2_FILENAME_VERSIONED, SF2_FILENAME_LEGACY):
        candidate = app_dir / name
        if candidate.is_file():
            return candidate.resolve()

    return None


def get_download_target_dir() -> Path:
    """Directory where soundfont should be downloaded (MaestroCommon)."""
    return _get_maestro_common_dir()


def download_soundfont(
    target_dir: Optional[Path] = None,
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> Optional[Path]:
    """
    Download LotroInstruments.sf2 to target_dir (default: MaestroCommon).
    Verifies SHA256. Returns Path to file on success, None on failure.
    progress_callback: optional (current_bytes, total_bytes) -> None, total may be -1
    """
    target_dir = target_dir or get_download_target_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    target_file = target_dir / SF2_FILENAME_VERSIONED
    temp_file = target_dir / (SF2_FILENAME_VERSIONED + ".tmp")

    def report_progress(current: int, total: int) -> None:
        if progress_callback:
            progress_callback(current, total)

    try:
        with urllib.request.urlopen(SF2_URL, timeout=60) as resp:
            total = int(resp.headers.get("Content-Length", -1))
            chunk_size = 1024 * 64
            downloaded = 0
            hasher = hashlib.sha256()
            with open(temp_file, "wb") as f:
                while True:
                    chunk = resp.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    hasher.update(chunk)
                    downloaded += len(chunk)
                    report_progress(downloaded, total)

        digest = hasher.hexdigest()
        if digest.lower() != EXPECTED_SHA256.lower():
            temp_file.unlink(missing_ok=True)
            return None

        temp_file.rename(target_file)
        return target_file.resolve()
    except Exception:
        temp_file.unlink(missing_ok=True)
        raise
