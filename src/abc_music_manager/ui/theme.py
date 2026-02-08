"""
Dark theme (DECISIONS 025). In-code palette and QSS for PySide6.
Used when Status.color or other UI elements are NULL (DECISIONS 018).
"""

from pathlib import Path

from PySide6.QtGui import QPalette, QColor, QFont
from PySide6.QtWidgets import QApplication

_theme_dir = Path(__file__).resolve().parent
# Plain absolute path for QSS url() — file:// causes Qt to concatenate with cwd
_checkmark_url = str((_theme_dir / "checkmark.svg").resolve()).replace("\\", "/")


# --- Dark palette ---
COLOR_BACKGROUND = "#0d0b14"
COLOR_SURFACE = "#12101a"
COLOR_OUTLINE = "#3d3654"
COLOR_OUTLINE_VARIANT = "#4a4260"
COLOR_PRIMARY = "#c9a227"
COLOR_TITLE_BAR = "#1a1533"
COLOR_ON_PRIMARY = "#0d0b14"
COLOR_ON_SURFACE = "#e8e4dc"
COLOR_TEXT_HEADER = "#e8d4a0"
COLOR_TEXT_SECONDARY = "#b4a8a8"
COLOR_TEXT_DISABLED = "#5c5460"
COLOR_ERROR = "#7a3030"
COLOR_SURFACE_VARIANT = "#1e1a2e"
# Softer highlight for selection/focus (avoids bright yellow on tables)
COLOR_HIGHLIGHT = "#3d3654"
COLOR_HIGHLIGHT_TEXT = "#e8e4dc"

# Status circle diameter in px. Used wherever a status is shown (library, settings, etc.). Change to resize globally.
STATUS_CIRCLE_DIAMETER = 12

# Status badge defaults when Status.color is NULL
STATUS_BADGE_NEW = "#4a4260"
STATUS_BADGE_TESTING = "#c9a227"
STATUS_BADGE_READY = "#2d4a2d"


def dark_palette() -> QPalette:
    """Build QPalette for dark theme."""
    p = QPalette()
    p.setColor(QPalette.ColorRole.Window, QColor(COLOR_BACKGROUND))
    p.setColor(QPalette.ColorRole.WindowText, QColor(COLOR_ON_SURFACE))
    p.setColor(QPalette.ColorRole.Base, QColor(COLOR_SURFACE))
    p.setColor(QPalette.ColorRole.AlternateBase, QColor(COLOR_SURFACE_VARIANT))
    p.setColor(QPalette.ColorRole.Text, QColor(COLOR_ON_SURFACE))
    p.setColor(QPalette.ColorRole.Button, QColor(COLOR_SURFACE))
    p.setColor(QPalette.ColorRole.ButtonText, QColor(COLOR_ON_SURFACE))
    p.setColor(QPalette.ColorRole.BrightText, QColor(COLOR_TEXT_HEADER))
    p.setColor(QPalette.ColorRole.Highlight, QColor(COLOR_HIGHLIGHT))
    p.setColor(QPalette.ColorRole.HighlightedText, QColor(COLOR_HIGHLIGHT_TEXT))
    p.setColor(QPalette.ColorRole.Link, QColor(COLOR_PRIMARY))
    p.setColor(QPalette.ColorRole.PlaceholderText, QColor(COLOR_TEXT_DISABLED))
    return p


def dark_stylesheet() -> str:
    """QSS for main window, menus, buttons, tables, inputs."""
    return f"""
        QMainWindow, QWidget {{
            background-color: {COLOR_BACKGROUND};
        }}
        QMenuBar {{
            background-color: {COLOR_TITLE_BAR};
            color: {COLOR_TEXT_HEADER};
        }}
        QMenuBar::item:selected {{
            background-color: {COLOR_OUTLINE_VARIANT};
        }}
        QMenu {{
            background-color: {COLOR_SURFACE};
            color: {COLOR_ON_SURFACE};
        }}
        QMenu::item:selected {{
            background-color: {COLOR_OUTLINE_VARIANT};
        }}
        QPushButton {{
            background-color: {COLOR_SURFACE};
            color: {COLOR_ON_SURFACE};
            border: 1px solid {COLOR_OUTLINE};
            border-radius: 4px;
        }}
        QPushButton:hover {{
            border-color: {COLOR_PRIMARY};
        }}
        QPushButton:pressed {{
            background-color: {COLOR_OUTLINE_VARIANT};
        }}
        QLineEdit, QPlainTextEdit, QTextEdit {{
            background-color: {COLOR_SURFACE};
            color: {COLOR_ON_SURFACE};
            border: 1px solid {COLOR_OUTLINE};
            border-radius: 4px;
        }}
        QSpinBox, QComboBox {{
            background-color: {COLOR_SURFACE};
            color: {COLOR_ON_SURFACE};
            border: 1px solid {COLOR_OUTLINE};
            border-radius: 4px;
            padding: 2px;
            min-height: 1.2em;
        }}
        QSpinBox::up-button, QSpinBox::down-button {{
            subcontrol-origin: border;
            background-color: {COLOR_OUTLINE_VARIANT};
            border: none;
            width: 18px;
        }}
        QSpinBox::up-button {{
            subcontrol-position: top right;
            border-top-right-radius: 3px;
        }}
        QSpinBox::down-button {{
            subcontrol-position: bottom right;
            border-bottom-right-radius: 3px;
        }}
        QSpinBox::up-button:hover, QSpinBox::down-button:hover {{
            background-color: {COLOR_OUTLINE};
        }}
        QSpinBox:disabled {{
            background-color: {COLOR_SURFACE_VARIANT};
            color: {COLOR_TEXT_DISABLED};
            border-color: {COLOR_OUTLINE};
        }}
        QSpinBox:disabled::up-button, QSpinBox:disabled::down-button {{
            background-color: {COLOR_OUTLINE};
            color: {COLOR_TEXT_DISABLED};
        }}
        QComboBox::drop-down {{
            subcontrol-origin: padding;
            subcontrol-position: top right;
            width: 20px;
            border-left: 1px solid {COLOR_OUTLINE};
            border-top-right-radius: 3px;
            border-bottom-right-radius: 3px;
            background-color: {COLOR_OUTLINE_VARIANT};
        }}
        QComboBox::drop-down:hover {{
            background-color: {COLOR_OUTLINE};
        }}
        QComboBox QAbstractItemView {{
            background-color: {COLOR_SURFACE};
            color: {COLOR_ON_SURFACE};
            selection-background-color: {COLOR_OUTLINE_VARIANT};
        }}
        QTableView {{
            background-color: {COLOR_SURFACE};
            color: {COLOR_ON_SURFACE};
            gridline-color: {COLOR_OUTLINE};
        }}
        QTableView::item:selected {{
            background-color: {COLOR_OUTLINE_VARIANT};
            color: {COLOR_ON_SURFACE};
        }}
        QTableView::item:selected:focus, QTableView::item:focus {{
            background-color: {COLOR_OUTLINE_VARIANT};
            color: {COLOR_ON_SURFACE};
            outline: none;
            border: 1px solid {COLOR_OUTLINE};
        }}
        QTableWidget {{
            background-color: {COLOR_SURFACE};
            color: {COLOR_ON_SURFACE};
            gridline-color: {COLOR_OUTLINE};
        }}
        QTableWidget::item:selected {{
            background-color: {COLOR_OUTLINE_VARIANT};
            color: {COLOR_ON_SURFACE};
        }}
        QTableWidget::item:selected:focus, QTableWidget::item:focus {{
            background-color: {COLOR_OUTLINE_VARIANT};
            color: {COLOR_ON_SURFACE};
            outline: none;
            border: 1px solid {COLOR_OUTLINE};
        }}
        QHeaderView::section {{
            background-color: {COLOR_TITLE_BAR};
            color: {COLOR_TEXT_HEADER};
            padding: 4px;
        }}
        QTabWidget::pane {{
            border: 1px solid {COLOR_OUTLINE};
            background-color: {COLOR_SURFACE};
        }}
        QTabBar::tab {{
            background-color: {COLOR_TITLE_BAR};
            color: {COLOR_TEXT_SECONDARY};
            padding: 8px 16px;
        }}
        QTabBar::tab:selected {{
            color: {COLOR_TEXT_HEADER};
        }}
        QLabel {{
            color: {COLOR_ON_SURFACE};
        }}
        QCheckBox {{
            color: {COLOR_ON_SURFACE};
        }}
        QCheckBox::indicator {{
            width: 16px;
            height: 16px;
            border: 2px solid {COLOR_OUTLINE};
            background-color: {COLOR_SURFACE};
            border-radius: 3px;
        }}
        QCheckBox::indicator:checked {{
            background-color: {COLOR_SURFACE};
            border: 2px solid {COLOR_PRIMARY};
            image: url("{_checkmark_url}");
        }}
        QCheckBox::indicator:hover {{
            border-color: {COLOR_PRIMARY};
        }}
        QListWidget {{
            background-color: {COLOR_SURFACE};
            color: {COLOR_ON_SURFACE};
        }}
        QListWidget::item:selected {{
            background-color: {COLOR_OUTLINE_VARIANT};
        }}
        QScrollBar:vertical {{
            background: {COLOR_SURFACE};
            width: 10px;
            border-radius: 2px;
        }}
        QScrollBar::handle:vertical {{
            background: {COLOR_OUTLINE_VARIANT};
            border-radius: 2px;
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0;
        }}
    """


def apply_theme(app: QApplication) -> None:
    """Apply dark theme and base font size to the application."""
    from PySide6.QtGui import QFontDatabase
    from ..services.preferences import get_base_font_size
    app.setPalette(dark_palette())
    app.setStyleSheet(dark_stylesheet())
    size = get_base_font_size()
    if size > 0:
        font = QFont(app.font())
        font.setPointSize(size)
        app.setFont(font)
    else:
        app.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont))
