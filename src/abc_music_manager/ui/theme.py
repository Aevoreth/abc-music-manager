"""
Dark theme (DECISIONS 025). In-code palette and QSS for PySide6.
Used when Status.color or other UI elements are NULL (DECISIONS 018).
"""

from pathlib import Path

from PySide6.QtCore import QObject, QEvent
from PySide6.QtGui import QPalette, QColor, QFont
from PySide6.QtWidgets import QApplication, QSpinBox

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
        /* Match spin box edit area to text boxes (internal QLineEdit can ignore parent styles on some platforms) */
        QSpinBox QLineEdit {{
            background-color: {COLOR_SURFACE};
            color: {COLOR_ON_SURFACE};
            border: none;
            border-radius: 3px;
            selection-background-color: {COLOR_OUTLINE_VARIANT};
            selection-color: {COLOR_ON_SURFACE};
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
            border-top: none;
            top: -1px;
        }}
        QTabBar::tab {{
            background-color: {COLOR_SURFACE_VARIANT};
            color: {COLOR_TEXT_SECONDARY};
            padding: 10px 20px;
            margin-right: 2px;
            border: 1px solid {COLOR_OUTLINE};
            border-bottom: none;
            border-top-left-radius: 6px;
            border-top-right-radius: 6px;
            min-width: 80px;
            font-weight: bold;
        }}
        QTabBar::tab:hover {{
            background-color: {COLOR_OUTLINE_VARIANT};
            color: {COLOR_ON_SURFACE};
        }}
        QTabBar::tab:selected {{
            background-color: {COLOR_SURFACE};
            color: {COLOR_TEXT_HEADER};
            font-weight: bold;
            border-color: {COLOR_OUTLINE};
            border-bottom: 1px solid {COLOR_SURFACE};
            margin-bottom: -1px;
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
            background-color: {COLOR_TITLE_BAR};
            color: {COLOR_ON_SURFACE};
            padding: 4px;
            border: 1px solid {COLOR_OUTLINE};
            border-radius: 6px;
            outline: none;
        }}
        QListWidget::viewport {{
            background-color: transparent;
        }}
        QListWidget::item {{
            background-color: {COLOR_SURFACE_VARIANT};
            color: {COLOR_TEXT_SECONDARY};
            padding: 10px 16px;
            margin: 2px 0;
            border: 1px solid {COLOR_OUTLINE};
            border-radius: 6px;
            min-height: 1.2em;
        }}
        QListWidget::item:hover {{
            background-color: {COLOR_OUTLINE_VARIANT};
            color: {COLOR_ON_SURFACE};
        }}
        QListWidget::item:selected, QListWidget::item:selected:focus, QListWidget::item:selected:active {{
            background-color: {COLOR_SURFACE};
            color: {COLOR_TEXT_HEADER};
            font-weight: bold;
            border-color: {COLOR_OUTLINE};
        }}
        /* Side tabs: rounded on left only, selected tab connects to content on the right */
        QListWidget#nav_list {{
            background-color: {COLOR_TITLE_BAR};
            padding: 4px 0 4px 4px;
            border: 1px solid {COLOR_OUTLINE};
            border-right: none;
            border-top-left-radius: 6px;
            border-bottom-left-radius: 6px;
            border-top-right-radius: 0;
            border-bottom-right-radius: 0;
        }}
        QListWidget#nav_list::viewport {{
            background-color: {COLOR_TITLE_BAR};
        }}
        QListWidget#nav_list::item {{
            background-color: {COLOR_SURFACE_VARIANT};
            color: {COLOR_TEXT_SECONDARY};
            padding: 0px 10px;
            margin: 4px 2px 4px 0;
            border: 1px solid {COLOR_OUTLINE};
            border-top-left-radius: 6px;
            border-bottom-left-radius: 6px;
            border-top-right-radius: 0;
            border-bottom-right-radius: 0;
            min-height: 0;
            font-weight: bold;
        }}
        QListWidget#nav_list::item:hover {{
            background-color: {COLOR_OUTLINE_VARIANT};
            color: {COLOR_ON_SURFACE};
        }}
        QListWidget#nav_list::item:selected, QListWidget#nav_list::item:selected:focus, QListWidget#nav_list::item:selected:active {{
            background-color: {COLOR_SURFACE};
            color: {COLOR_TEXT_HEADER};
            font-weight: bold;
            border-right: 1px solid {COLOR_SURFACE};
            margin-right: -1px;
        }}
        QStackedWidget#main_content {{
            background-color: {COLOR_SURFACE};
            border-left: 1px solid {COLOR_OUTLINE};
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
        QScrollBar:horizontal {{
            background: {COLOR_SURFACE};
            height: 10px;
            border-radius: 2px;
        }}
        QScrollBar::handle:horizontal {{
            background: {COLOR_OUTLINE_VARIANT};
            border-radius: 2px;
        }}
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
            width: 0;
        }}
    """


# Styles applied programmatically to spin box and its line edit so they match QLineEdit (stylesheet alone is unreliable on some platforms)
_SPINBOX_LINEEDIT_STYLESHEET = (
    f"background-color: {COLOR_SURFACE}; color: {COLOR_ON_SURFACE}; border: none;"
    f" selection-background-color: {COLOR_OUTLINE_VARIANT}; selection-color: {COLOR_ON_SURFACE};"
)
_SPINBOX_STYLESHEET = (
    f"QSpinBox {{"
    f" background-color: {COLOR_SURFACE}; color: {COLOR_ON_SURFACE};"
    f" border: 1px solid {COLOR_OUTLINE}; border-radius: 4px;"
    f" padding: 4px; padding-right: 22px; min-height: 1.2em;"
    f"}}"
    f"QSpinBox:disabled {{"
    f" background-color: {COLOR_SURFACE_VARIANT}; color: {COLOR_TEXT_DISABLED}; border-color: {COLOR_OUTLINE};"
    f"}}"
    f"QSpinBox::up-button, QSpinBox::down-button {{"
    f" subcontrol-origin: border; background-color: {COLOR_OUTLINE_VARIANT}; border: none; width: 18px;"
    f"}}"
    f"QSpinBox::up-button {{ subcontrol-position: top right; border-top-right-radius: 3px; }}"
    f"QSpinBox::down-button {{ subcontrol-position: bottom right; border-bottom-right-radius: 3px; }}"
    f"QSpinBox::up-button:hover, QSpinBox::down-button:hover {{ background-color: {COLOR_OUTLINE}; }}"
)


def _apply_spinbox_theme(spinbox: QSpinBox) -> None:
    """Force spin box and its line edit to match text box styling (background, font color)."""
    if spinbox.property("_theme_styled"):
        return
    spinbox.setStyleSheet(_SPINBOX_STYLESHEET)
    le = spinbox.lineEdit()
    if le:
        le.setStyleSheet(_SPINBOX_LINEEDIT_STYLESHEET)
        p = le.palette()
        p.setColor(p.ColorRole.Base, QColor(COLOR_SURFACE))
        p.setColor(p.ColorRole.Text, QColor(COLOR_ON_SURFACE))
        le.setPalette(p)
    spinbox.setProperty("_theme_styled", True)


class _SpinBoxThemeFilter(QObject):
    """Event filter that applies theme to QSpinBox when shown (so internal line edit matches text boxes)."""

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.Show and isinstance(obj, QSpinBox):
            _apply_spinbox_theme(obj)
        return False


def apply_theme(app: QApplication) -> None:
    """Apply dark theme and base font size to the application."""
    from PySide6.QtGui import QFontDatabase
    from ..services.preferences import get_base_font_size
    app.setPalette(dark_palette())
    app.setStyleSheet(dark_stylesheet())
    app.installEventFilter(_SpinBoxThemeFilter(app))
    # Style any spin boxes that already exist (e.g. if theme is reapplied)
    for w in app.topLevelWidgets():
        for spin in w.findChildren(QSpinBox):
            _apply_spinbox_theme(spin)
    size = get_base_font_size()
    if size > 0:
        font = QFont(app.font())
        font.setPointSize(size)
        app.setFont(font)
    else:
        app.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont))
