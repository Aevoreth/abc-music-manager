"""
LOTRO image-accurate UI theme (DECISIONS 025).
Based on actual in-game UI: Custom UI dialog, Quest Log. Dark, heavy, utilitarian MMO UI.
Used when Status.color or other UI elements are NULL (DECISIONS 018).
"""

import flet as ft


# --- Image-accurate LOTRO palette (in-game windows) ---

# Backgrounds: #000000 – #0b0d10
COLOR_BACKGROUND = "#0b0d10"             # Near-black (main window)
COLOR_SURFACE = "#080a0e"                # Near-black panel interior

# Frames (steel / iron): #3e434a, #4a5058
COLOR_OUTLINE = "#3e434a"
COLOR_OUTLINE_VARIANT = "#4a5058"

# Accents
COLOR_PRIMARY = "#b7a15a"                # Gold (primary actions, headers)
COLOR_TITLE_BAR = "#1f2f5a"              # Deep blue (title bars)
COLOR_ON_PRIMARY = "#0b0d10"             # Dark text on gold
COLOR_PRIMARY_CONTAINER = "#0f1218"       # Dark for chips/badges
COLOR_ON_PRIMARY_CONTAINER = "#c8b46a"
COLOR_SURFACE_VARIANT = "#1f2f5a"         # Deep blue (table headers, rail)

# Text
COLOR_TEXT_HEADER = "#c8b46a"             # Headers (gold)
COLOR_ON_SURFACE = "#e0e0e0"             # Body
COLOR_TEXT_SECONDARY = "#b8b8b8"          # Secondary
COLOR_TEXT_DISABLED = "#6b6b6b"          # Disabled

# Error & overlay
COLOR_ERROR = "#6b3030"
COLOR_ON_ERROR = "#e0e0e0"
COLOR_SCRIM = "#050608"                  # Modal barrier


# Layout: desktop-first, minimal rounding, thick metal frames
BORDER_RADIUS = 2
SPACING_TIGHT = 2
SPACING_DEFAULT = 4
SPACING_SECTION = 6
PADDING_TIGHT = 3
PADDING_DEFAULT = 5
PADDING_SECTION = 6


def _header_text_style() -> ft.TextStyle:
    """Serif header with slight halo (LOTRO style)."""
    return ft.TextStyle(
        color=COLOR_TEXT_HEADER,
        font_family="Georgia",
        weight=ft.FontWeight.W_500,
        shadow=ft.BoxShadow(blur_radius=1, color="#1a1810", offset=ft.Offset(0, 0)),
    )


def _color_scheme() -> ft.ColorScheme:
    """Full ColorScheme — every role explicit so theme applies everywhere."""
    return ft.ColorScheme(
        primary=COLOR_PRIMARY,
        on_primary=COLOR_ON_PRIMARY,
        primary_container=COLOR_PRIMARY_CONTAINER,
        on_primary_container=COLOR_ON_PRIMARY_CONTAINER,
        secondary=COLOR_OUTLINE_VARIANT,
        on_secondary=COLOR_ON_SURFACE,
        secondary_container=COLOR_SURFACE_VARIANT,
        on_secondary_container=COLOR_TEXT_HEADER,
        tertiary=COLOR_OUTLINE_VARIANT,
        on_tertiary=COLOR_ON_SURFACE,
        tertiary_container=COLOR_SURFACE_VARIANT,
        on_tertiary_container=COLOR_ON_SURFACE,
        error=COLOR_ERROR,
        on_error=COLOR_ON_ERROR,
        error_container=COLOR_SURFACE_VARIANT,
        on_error_container=COLOR_ON_SURFACE,
        surface=COLOR_SURFACE,
        on_surface=COLOR_ON_SURFACE,
        on_surface_variant=COLOR_TEXT_SECONDARY,
        surface_container_lowest=COLOR_BACKGROUND,
        surface_container_low=COLOR_BACKGROUND,
        surface_container=COLOR_SURFACE,
        surface_container_high=COLOR_SURFACE_VARIANT,
        surface_container_highest=COLOR_SURFACE_VARIANT,
        surface_dim=COLOR_BACKGROUND,
        surface_bright=COLOR_SURFACE_VARIANT,
        outline=COLOR_OUTLINE,
        outline_variant=COLOR_OUTLINE_VARIANT,
        shadow=COLOR_BACKGROUND,
        scrim=COLOR_SCRIM,
        inverse_surface=COLOR_SURFACE_VARIANT,
        on_inverse_surface=COLOR_TEXT_HEADER,
        inverse_primary=COLOR_PRIMARY,
    )


def dark_theme() -> ft.Theme:
    """Global LOTRO image-accurate theme for the entire app."""
    return ft.Theme(
        color_scheme=_color_scheme(),
        use_material3=True,
        visual_density=ft.VisualDensity.COMPACT,
        font_family="Georgia",  # Serif only (no modern sans-serif)
        # Page/chrome
        scaffold_bgcolor=COLOR_BACKGROUND,
        canvas_color=COLOR_BACKGROUND,
        card_bgcolor=COLOR_SURFACE,
        # Dividers and borders (steel frames)
        divider_color=COLOR_OUTLINE,
        hint_color=COLOR_TEXT_SECONDARY,
        focus_color=COLOR_PRIMARY,
        hover_color=COLOR_OUTLINE_VARIANT,
        splash_color=COLOR_PRIMARY,
        disabled_color=COLOR_TEXT_DISABLED,
        unselected_control_color=COLOR_TEXT_DISABLED,
        highlight_color=COLOR_PRIMARY,
        secondary_header_color=COLOR_TITLE_BAR,
        # Text: serif, body #e0e0e0, headers gold with slight halo
        text_theme=ft.TextTheme(
            body_large=ft.TextStyle(color=COLOR_ON_SURFACE, font_family="Georgia"),
            body_medium=ft.TextStyle(color=COLOR_ON_SURFACE, font_family="Georgia"),
            body_small=ft.TextStyle(color=COLOR_ON_SURFACE, font_family="Georgia"),
            title_large=_header_text_style(),
            title_medium=_header_text_style(),
            title_small=_header_text_style(),
            label_large=ft.TextStyle(color=COLOR_ON_SURFACE, font_family="Georgia"),
            label_medium=ft.TextStyle(color=COLOR_ON_SURFACE, font_family="Georgia"),
            label_small=ft.TextStyle(color=COLOR_TEXT_SECONDARY, font_family="Georgia"),
        ),
        primary_text_theme=ft.TextTheme(
            body_large=ft.TextStyle(color=COLOR_ON_SURFACE, font_family="Georgia"),
            title_medium=_header_text_style(),
        ),
        # Dialogs — near-black interior, deep blue title bar feel via content
        dialog_theme=ft.DialogTheme(
            bgcolor=COLOR_SURFACE,
            barrier_color=COLOR_SCRIM,
            title_text_style=ft.TextStyle(
                color=COLOR_TEXT_HEADER,
                size=18,
                font_family="Georgia",
                weight=ft.FontWeight.W_500,
                shadow=ft.BoxShadow(blur_radius=1, color="#1a1810", offset=ft.Offset(0, 0)),
            ),
            content_text_style=ft.TextStyle(color=COLOR_ON_SURFACE, font_family="Georgia"),
            icon_color=COLOR_PRIMARY,
        ),
        # Navigation rail — deep blue (title bar), gold selected
        navigation_rail_theme=ft.NavigationRailTheme(
            bgcolor=COLOR_TITLE_BAR,
            indicator_color=COLOR_OUTLINE_VARIANT,
            selected_label_text_style=ft.TextStyle(color=COLOR_PRIMARY, font_family="Georgia"),
            unselected_label_text_style=ft.TextStyle(color=COLOR_TEXT_SECONDARY, font_family="Georgia"),
        ),
        # Data table — deep blue header row, near-black data, thin steel dividers
        data_table_theme=ft.DataTableTheme(
            heading_row_color=COLOR_TITLE_BAR,
            data_row_color=COLOR_SURFACE,
            heading_text_style=ft.TextStyle(color=COLOR_TEXT_HEADER, font_family="Georgia"),
            data_text_style=ft.TextStyle(color=COLOR_ON_SURFACE, font_family="Georgia"),
            data_row_min_height=24,
            heading_row_height=28,
            divider_thickness=1,
        ),
        # Buttons: inset, dark fill, metallic border; gold border for primary only
        filled_button_theme=ft.FilledButtonTheme(
            style=ft.ButtonStyle(
                color=COLOR_TEXT_HEADER,
                bgcolor=COLOR_SURFACE,
                side=ft.BorderSide(2, COLOR_PRIMARY),
                overlay_color=COLOR_OUTLINE_VARIANT,
            ),
        ),
        text_button_theme=ft.TextButtonTheme(
            style=ft.ButtonStyle(
                color=COLOR_PRIMARY,
                text_style=ft.TextStyle(font_family="Georgia"),
            ),
        ),
        outlined_button_theme=ft.OutlinedButtonTheme(
            style=ft.ButtonStyle(
                color=COLOR_ON_SURFACE,
                side=ft.BorderSide(1, COLOR_OUTLINE),
            ),
        ),
        icon_button_theme=ft.IconButtonTheme(
            style=ft.ButtonStyle(color=COLOR_ON_SURFACE),
        ),
        # Inputs
        dropdown_theme=ft.DropdownTheme(
            text_style=ft.TextStyle(color=COLOR_ON_SURFACE, font_family="Georgia"),
        ),
        # Switch — steel track, gold thumb
        switch_theme=ft.SwitchTheme(
            track_color=COLOR_OUTLINE_VARIANT,
            thumb_color=COLOR_PRIMARY,
        ),
        # Snackbar
        snackbar_theme=ft.SnackBarTheme(
            bgcolor=COLOR_SURFACE_VARIANT,
            content_text_style=ft.TextStyle(color=COLOR_ON_SURFACE, font_family="Georgia"),
            action_text_color=COLOR_PRIMARY,
        ),
        # Progress
        progress_indicator_theme=ft.ProgressIndicatorTheme(
            color=COLOR_PRIMARY,
            linear_track_color=COLOR_OUTLINE_VARIANT,
            circular_track_color=COLOR_OUTLINE_VARIANT,
        ),
        # Scrollbars — narrow, dark
        scrollbar_theme=ft.ScrollbarTheme(
            thumb_color=COLOR_OUTLINE_VARIANT,
            track_color=COLOR_SURFACE,
            track_visibility=True,
            thickness=6,
            radius=BORDER_RADIUS,
        ),
    )


def apply_theme(page: ft.Page) -> None:
    """Apply LOTRO image-accurate theme to the entire app."""
    t = dark_theme()
    page.theme = t
    page.dark_theme = t
    page.theme_mode = ft.ThemeMode.DARK
    page.bgcolor = COLOR_BACKGROUND
    page.padding = ft.padding.all(PADDING_DEFAULT)
