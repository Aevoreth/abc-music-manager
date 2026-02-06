# Previous implementation (Flet)

This folder contains the **previous** ABC Music Manager codebase, which used **Flet** for the UI. It was archived here when the project switched to **PySide6 (Qt for Python)** for better theming and styling (see DECISIONS 026).

- **main.py** — Flet app entry point
- **src/** — Flet-based UI, scanner, parser, DB layer
- **scripts/** — Schema verification and other utilities
- **requirements.txt** — Old deps (flet)

This code is kept for reference only. The active application will be rebuilt from scratch using PySide6. Design docs (REQUIREMENTS.md, DATA_MODEL.md, DECISIONS.md, etc.) remain the source of truth.
