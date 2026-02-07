# Skinpacks

Skinpacks provide consistent UI behavior: palette, QSS, status badge defaults, and related theme-derived values (see DECISIONS 018, 025).

The application expects skin data to live in **skin directories** under `src/abc_music_manager/ui/skins/`. That folder is reserved for skin directories only (no Python or other app code there). Each skinpack can provide:

- **QPalette** (or factory)
- **Stylesheet** string (QSS)
- Optional overrides for status badge colors and other theme-derived values
