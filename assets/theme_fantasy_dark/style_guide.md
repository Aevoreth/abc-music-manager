# Fantasy Dark Theme — Style Guide

Original high-fantasy UI theme: dark carved stone, aged metal trim, subtle elven/dwarven filigree and blue rune/gem accents. Readability first; all text on dark panels must meet contrast requirements.

---

## 1. Color palette

All hex values and where they are used. Map these to Qt `QPalette` roles where applicable.

| Role | Hex | Use |
|------|-----|-----|
| **Primary background** (window, major panels) | `#2E2824` | QMainWindow, QGroupBox; dark warm brown-grey, textured like stone or oxidized bronze. |
| **Panel background** (inner widgets) | `#211D1A` | QLineEdit, QTextEdit, QComboBox dropdown, QTableView cells, QListWidget, button faces; polished dark stone/obsidian. |
| **Border metal** (trim, frames) | `#8B6F4D` | All prominent borders, button rims, decorative filigree; brushed antique gold/bronze, muted and aged. |
| **Highlight / selection** (active state) | `#3A89C9` | Selected list/table rows, QSlider/QProgressBar fill, check/radio indicators; vibrant glowing blue. |
| **Accent** (runes, subtle glows, focus) | `#6FB3D2` | Focus ring, small decorative elements, optional corner ornaments; lighter teal-blue. |
| **Text primary** | `#E0DBCF` | Labels, button text, input text; light parchment off-white. High contrast on dark backgrounds. |
| **Text secondary** | `#A89F8F` | Secondary labels, hints. |
| **Text disabled** | `#6B6358` | Disabled widget text; desaturated grey. |

### QPalette mapping (for theme.py)

- **Window** → `#2E2824`
- **WindowText** → `#E0DBCF`
- **Base** → `#211D1A`
- **AlternateBase** → slightly lighter than Base for alternating rows (e.g. `#252119`)
- **Text** → `#E0DBCF`
- **Button** → `#211D1A`
- **ButtonText** → `#E0DBCF`
- **BrightText** → `#E0DBCF` (headers)
- **Highlight** → `#3A89C9`
- **HighlightedText** → `#E0DBCF`
- **Link** → `#6FB3D2`
- **PlaceholderText** → `#6B6358`

---

## 2. Typography

- **Title** (QGroupBox, window titles, headers): Clean, legible sans-serif; slightly wider tracking or subtle bold; historical/robust feel.  
  **Font stack:** `"Open Sans", "Roboto", Arial, sans-serif`  
  **Color:** Text primary (`#E0DBCF`).

- **Body** (labels, buttons, inputs, table/list text): Clear sans-serif; high legibility at small sizes.  
  **Font stack:** `"Segoe UI", Arial, sans-serif`  
  **Color:** Text primary on dark panels.

Prioritise readability over ornamentation; avoid ornate serif for UI text. Font color is always text primary (or secondary/disabled as above) on dark backgrounds.

---

## 3. Spacing and radii

- **Corner radii:** 2–4px on functional elements (buttons, input fields, inner panels) for a soft “carved” feel. Ornate metallic frames may have sharper corners where filigree defines the shape; 9-slice assets can override.
- **Padding / margins:** Generous internal padding and clear separation between components.
  - **Tight:** 4px
  - **Default:** 8px
  - **Section:** 12px

Use consistent steps so layouts stay aligned. 9-slice border images may define their own effective radii.

---

## 4. Material rules

- **Stone:** Dark, subtly textured (noise/grain). Use for QMainWindow background, QGroupBox, scrollbar track, progress trough, and general panel backings.
- **Aged metal:** Brushed gold/bronze with bevel or emboss. Use for borders, button rims, slider/scrollbar handles, and structural trim. Lighting direction: top-left.
- **Parchment:** Evoked by **text primary** color on dark panels; no separate leather texture required unless specified.
- **Gems / runes:** Glowing blue (highlight `#3A89C9` and accent `#6FB3D2`) for selection, focus, and small decorative motifs. Keep subtle so they don’t overpower.

---

## 5. Widget states

| State | Appearance |
|-------|-------------|
| **Normal** | Dark panels, metallic borders, light text as in palette. |
| **Hover** | Metallic rim brightens slightly and/or subtle accent blue glow at border. |
| **Pressed** | Slightly sunken look; more pronounced inner shadow. |
| **Checked** | Highlight blue (`#3A89C9`) for checkbox/radio indicator; optional subtle glow. |
| **Disabled** | Desaturated; reduced or no metallic sheen; text secondary grey (`#6B6358`). |
| **Focus** | Thin accent blue (`#6FB3D2`) outline or glow around focused input/button. |

Apply consistently so users can tell interactive vs disabled vs selected at a glance.

---

## 6. Widget-specific visuals (for assets and QSS)

- **Buttons (QPushButton):** Dark stone face, thin antique-gold rim, bevel; optional engraved corners. Text primary.
- **Inputs (QLineEdit, QComboBox, QDateEdit, etc.):** Inset carved slot; polished dark interior; thin metallic border. Focus = accent blue ring. Combo drop-down arrow = small accent-blue glyph on dark button.
- **Sliders (QSlider):** Groove = metal channel. Handle = ornate gold/bronze knob (e.g. leaf/wing shape), optional small blue gem. Filled track = highlight blue.
- **Scrollbars (QScrollBar):** Track = dark textured stone channel. Handle = raised bronze grip. Arrows = simple triangular glyphs.
- **Progress (QProgressBar):** Trough = stone channel. Chunk = glowing highlight blue with slight texture (emitted light feel); keep separate from button visuals.
- **Tabs (QTabBar):** Raised carved plaques. Selected = brighter rim + subtle blue (accent) line.
- **Table / list / tree:** Dark background; blue selection highlight; headers = dark panel with light text and subtle metallic border. Optional alternating row tint.
- **Window / frame (QMainWindow, QGroupBox):** Carved golden filigree at corners; optional small accent blue ornament (e.g. top-left). Consistent lighting from top-left.

When generating or drawing assets: 9-slice borders wherever widgets need to scale; consistent corner motifs; no copying of third-party IP—original shapes only.
