"""Restore a dialog's last size, and keep it after the user resizes the window."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QWidget

# Padding so cards are not flush with the grid, plus the band combo, hint, and buttons.
_LAYOUT_EDITOR_CHROME_WIDTH = 64
_LAYOUT_EDITOR_CHROME_HEIGHT = 200


def layout_editor_size_for_slots(
    positions: list[tuple[int, int]],
    *,
    card_width: int,
    card_height: int,
    pixels_per_unit: int,
    floor_width: int,
    floor_height: int,
) -> tuple[int, int]:
    """Pixel size that shows every card, and is at least the floor size.

    ``positions`` are card origins in grid units. The grid centers that bounding
    box, so the view has to be at least as large as the span.
    """
    if not positions:
        return floor_width, floor_height
    min_x = min(x for x, _y in positions)
    max_x = max(x + card_width for x, _y in positions)
    min_y = min(y for _x, y in positions)
    max_y = max(y + card_height for _x, y in positions)
    width = (max_x - min_x) * pixels_per_unit + _LAYOUT_EDITOR_CHROME_WIDTH
    height = (max_y - min_y) * pixels_per_unit + _LAYOUT_EDITOR_CHROME_HEIGHT
    return max(floor_width, width), max(floor_height, height)


def restore_dialog_size(
    widget: QWidget,
    saved: dict[str, int] | None,
    default_width: int,
    default_height: int,
) -> None:
    """Apply a saved size, or the default, without exceeding the current screen."""
    width = saved["width"] if saved else default_width
    height = saved["height"] if saved else default_height
    width = max(width, widget.minimumWidth())
    height = max(height, widget.minimumHeight())
    screen = widget.screen() or QGuiApplication.primaryScreen()
    if screen is not None:
        avail = screen.availableGeometry()
        width = min(width, max(widget.minimumWidth(), avail.width() - 16))
        height = min(height, max(widget.minimumHeight(), avail.height() - 48))
    widget.resize(width, height)


class RememberDialogSize:
    """Mixin for a QDialog that remembers width and height.

    List this class before QDialog. Call ``_begin_size_memory`` at the end of
    ``__init__``, after ``setMinimumSize``.
    """

    def _begin_size_memory(
        self,
        saved: dict[str, int] | None,
        default_width: int,
        default_height: int,
        save: Callable[[int, int], None],
    ) -> None:
        self._dialog_size_save = save
        self._dialog_size_timer = QTimer(self)
        self._dialog_size_timer.setSingleShot(True)
        self._dialog_size_timer.timeout.connect(self._persist_dialog_size)
        # Ignore the resize Qt applies when the window is first shown.
        self._dialog_size_ready = False
        self._dialog_size_user_resized = False
        restore_dialog_size(self, saved, default_width, default_height)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        QTimer.singleShot(0, self._arm_dialog_size_memory)

    def _arm_dialog_size_memory(self) -> None:
        self._dialog_size_ready = True

    def _persist_dialog_size(self) -> None:
        width, height = self.width(), self.height()
        if width >= self.minimumWidth() and height >= self.minimumHeight():
            self._dialog_size_save(width, height)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if getattr(self, "_dialog_size_ready", False):
            self._dialog_size_user_resized = True
            self._dialog_size_timer.start(200)

    def hideEvent(self, event) -> None:
        # accept/reject hide the dialog and do not send closeEvent.
        if getattr(self, "_dialog_size_user_resized", False):
            self._dialog_size_timer.stop()
            self._persist_dialog_size()
        super().hideEvent(event)

    def closeEvent(self, event) -> None:
        if getattr(self, "_dialog_size_user_resized", False):
            self._dialog_size_timer.stop()
            self._persist_dialog_size()
        super().closeEvent(event)
