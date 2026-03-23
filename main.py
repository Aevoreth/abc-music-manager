#!/usr/bin/env python3
"""
ABC Music Manager — entry point.
"""

import json
import multiprocessing
import os
import sys
from pathlib import Path

# Allow running from repo root without installing package
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

# #region agent log
def _log(loc: str, msg: str, data: dict, hyp: str = "A") -> None:
    try:
        log_path = Path.cwd() / "debug-58ac41.log"
        with open(log_path, "a") as f:
            f.write(json.dumps({"sessionId":"58ac41","location":loc,"message":msg,"data":data,"hypothesisId":hyp,"timestamp":__import__("time").time()*1000})+'\n')
    except Exception:
        pass
# #endregion

from PySide6.QtWidgets import QApplication

from abc_music_manager.services.app_state import AppState
from abc_music_manager.services.preferences import ensure_default_lotro_root
from abc_music_manager.ui.theme import apply_theme
from abc_music_manager.ui.main_window import MainWindow


def main() -> None:
    # #region agent log
    cp = multiprocessing.current_process()
    _log("main.py:main", "App startup", {"pid": os.getpid(), "ppid": os.getppid(), "proc_name": cp.name, "frozen": getattr(sys, "frozen", False)}, "A")
    # #endregion
    app = QApplication(sys.argv)
    app.setApplicationName("ABC Music Manager")
    apply_theme(app)
    ensure_default_lotro_root()
    with AppState() as state:
        window = MainWindow(state)
        window.show()
        app.aboutToQuit.connect(window.playback_state.close)
        sys.exit(app.exec())


if __name__ == "__main__":
    multiprocessing.freeze_support()  # Required for PyInstaller on Windows: child runs target, not main()
    main()
