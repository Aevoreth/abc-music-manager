#!/usr/bin/env python3
"""
ABC Music Manager — entrypoint.
Ensures database is initialized, then runs the Flet app.
"""

import sys
from pathlib import Path

# Allow running as: python main.py (from project root)
root = Path(__file__).resolve().parent
if str(root) not in sys.path:
    sys.path.insert(0, str(root))

from src.abc_music_manager.db import init_database
from src.abc_music_manager.app import run_app


def main() -> None:
    # Ensure DB exists and schema is up to date (idempotent)
    conn = init_database()
    conn.close()
    run_app()


if __name__ == "__main__":
    main()
