"""
Band layout grid widget: dotted graph-paper background, draggable player cards.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import floor

from PySide6.QtWidgets import QWidget, QPushButton, QMenu
from PySide6.QtCore import Qt, QPoint, QRect, Signal
from PySide6.QtGui import QPainter, QColor, QPen, QFont, QFontMetrics

from .theme import (
    COLOR_SURFACE,
    COLOR_OUTLINE,
    COLOR_ON_SURFACE,
    COLOR_ERROR,
)

# Grid and card specs
CARD_WIDTH = 9
CARD_HEIGHT = 7
X_MIN, X_MAX = -145, 145
Y_MIN, Y_MAX = -105, 105
MAX_CARDS = 24
SPAWN_X, SPAWN_Y = -4, -3
PIXELS_PER_UNIT = 14


@dataclass
class LayoutCard:
    """A player card on the layout grid."""

    player_id: int
    player_name: str
    x: int
    y: int
    part_number: str = "###"
    part_name: str = "Misty Mountain Harp"
    instrument_name: str = "Misty Mountain Harp"


def _rects_overlap(
    x1: int, y1: int, w1: int, h1: int,
    x2: int, y2: int, w2: int, h2: int,
) -> bool:
    """Check if two axis-aligned rectangles overlap."""
    return not (x1 + w1 <= x2 or x2 + w2 <= x1 or y1 + h1 <= y2 or y2 + h2 <= y1)


class BandLayoutGridWidget(QWidget):
    """
    Custom widget: dotted grid background, draggable cards.
    Add Player button is a fixed overlay in the upper-left.
    """

    cardMoved = Signal(int, int, int)  # player_id, new_x, new_y
    cardDeleted = Signal(int)  # player_id
    cardEditRequested = Signal(int)  # player_id

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(300, 200)
        self.setMouseTracking(True)
        self._cards: list[LayoutCard] = []
        self._pan_x = 0.0
        self._pan_y = 0.0
        self._pixels_per_unit = PIXELS_PER_UNIT
        self._drag_start: QPoint | None = None
        self._pan_start: QPoint | None = None
        self._dragging_card: LayoutCard | None = None
        self._drag_card_start_x = 0
        self._drag_card_start_y = 0
        self._original_z_order: list[LayoutCard] = []

        self._add_player_btn = QPushButton("Add Player", self)
        self._add_player_btn.setFixedWidth(
            self._add_player_btn.fontMetrics().horizontalAdvance("Add Player") + 24
        )
        self._add_player_btn.move(8, 8)
        self._add_player_btn.raise_()

    def set_cards(self, cards: list[LayoutCard]) -> None:
        """Replace the card list."""
        self._cards = list(cards)
        self.update()

    def get_cards(self) -> list[LayoutCard]:
        """Return a copy of the card list."""
        return [LayoutCard(
            player_id=c.player_id,
            player_name=c.player_name,
            x=c.x,
            y=c.y,
            part_number=c.part_number,
            part_name=c.part_name,
            instrument_name=c.instrument_name,
        ) for c in self._cards]

    def add_card(self, card: LayoutCard) -> bool:
        """Add a card if under max. Returns True if added."""
        if len(self._cards) >= MAX_CARDS:
            return False
        self._cards.append(card)
        self.update()
        return True

    def remove_card(self, player_id: int) -> bool:
        """Remove card by player_id. Returns True if removed."""
        for i, c in enumerate(self._cards):
            if c.player_id == player_id:
                self._cards.pop(i)
                self.update()
                return True
        return False

    def _logical_to_view(self, lx: float, ly: float) -> tuple[float, float]:
        cx = self.width() / 2
        cy = self.height() / 2
        vx = (lx - self._pan_x) * self._pixels_per_unit + cx
        vy = (ly - self._pan_y) * self._pixels_per_unit + cy
        return vx, vy

    def _view_to_logical(self, vx: float, vy: float) -> tuple[float, float]:
        cx = self.width() / 2
        cy = self.height() / 2
        lx = (vx - cx) / self._pixels_per_unit + self._pan_x
        ly = (vy - cy) / self._pixels_per_unit + self._pan_y
        return lx, ly

    def _card_at(self, vx: float, vy: float) -> LayoutCard | None:
        """Return the topmost card containing the view point, or None."""
        lx, ly = self._view_to_logical(vx, vy)
        # Check in reverse order (topmost first)
        for c in reversed(self._cards):
            if (c.x <= lx < c.x + CARD_WIDTH and
                    c.y <= ly < c.y + CARD_HEIGHT):
                return c
        return None

    def has_any_overlap(self) -> bool:
        """Return True if any cards overlap."""
        for card in self._cards:
            if self._has_overlap(card):
                return True
        return False

    def _has_overlap(self, card: LayoutCard) -> bool:
        """Check if this card overlaps any other."""
        for other in self._cards:
            if other is card:
                continue
            if _rects_overlap(
                card.x, card.y, CARD_WIDTH, CARD_HEIGHT,
                other.x, other.y, CARD_WIDTH, CARD_HEIGHT,
            ):
                return True
        return False

    def _clamp_position(self, x: int, y: int) -> tuple[int, int]:
        x = max(X_MIN, min(X_MAX, x))
        y = max(Y_MIN, min(Y_MAX, y))
        return x, y

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._add_player_btn.raise_()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        # Background
        painter.fillRect(self.rect(), QColor(COLOR_SURFACE))

        # Dotted grid
        pen = QPen(QColor(COLOR_OUTLINE))
        pen.setWidth(1)
        painter.setPen(pen)

        lx_min = self._view_to_logical(0, 0)[0]
        lx_max = self._view_to_logical(self.width(), 0)[0]
        ly_min = self._view_to_logical(0, 0)[1]
        ly_max = self._view_to_logical(0, self.height())[1]

        for lx in range(int(floor(lx_min)), int(lx_max) + 2):
            for ly in range(int(floor(ly_min)), int(ly_max) + 2):
                vx, vy = self._logical_to_view(lx, ly)
                if 0 <= vx < self.width() and 0 <= vy < self.height():
                    painter.drawPoint(int(vx), int(vy))

        # Cards
        for card in self._cards:
            vx, vy = self._logical_to_view(card.x, card.y)
            cw = CARD_WIDTH * self._pixels_per_unit
            ch = CARD_HEIGHT * self._pixels_per_unit
            rect = QRect(int(vx), int(vy), int(cw), int(ch))

            overlap = self._has_overlap(card)
            if overlap:
                painter.setPen(QPen(QColor(COLOR_ERROR), 3))
            else:
                painter.setPen(QPen(QColor(COLOR_OUTLINE), 1))
            painter.setBrush(QColor(COLOR_SURFACE))
            painter.drawRoundedRect(rect, 4, 4)

            # Card content
            painter.setPen(QColor(COLOR_ON_SURFACE))
            margin = 4
            inner = rect.adjusted(margin, margin, -margin, -margin)

            # Top row: player name (simplified - no Edit/Delete buttons drawn, just text)
            font = painter.font()
            font.setPointSize(font.pointSize())
            painter.setFont(font)
            painter.drawText(inner, Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft, card.player_name)

            # Part number (large)
            big_font = QFont(font)
            big_font.setPointSize(font.pointSize() + 4)
            painter.setFont(big_font)
            fm = QFontMetrics(big_font)
            part_num_rect = inner.adjusted(0, fm.height() + 2, 0, 0)
            painter.drawText(part_num_rect, Qt.AlignmentFlag.AlignLeft, card.part_number)

            # Instrument / part name
            painter.setFont(font)
            inst_rect = inner.adjusted(0, fm.height() * 2 + 6, 0, 0)
            painter.drawText(inst_rect, Qt.AlignmentFlag.AlignLeft, card.instrument_name)

            small_font = QFont(font)
            small_font.setPointSize(max(8, font.pointSize() - 1))
            painter.setFont(small_font)
            part_rect = inner.adjusted(0, fm.height() * 3 + 10, 0, 0)
            painter.drawText(part_rect, Qt.AlignmentFlag.AlignLeft, card.part_name)

        self._add_player_btn.raise_()

    def contextMenuEvent(self, event) -> None:
        pos = event.pos()
        card = self._card_at(pos.x(), pos.y())
        if card:
            menu = QMenu(self)
            edit_action = menu.addAction("Edit")
            delete_action = menu.addAction("Delete")
            action = menu.exec(event.globalPos())
            if action == edit_action:
                self.cardEditRequested.emit(card.player_id)
            elif action == delete_action:
                self.cardDeleted.emit(card.player_id)
        else:
            super().contextMenuEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return

        pos = event.position().toPoint()
        if self._add_player_btn.geometry().contains(pos):
            super().mousePressEvent(event)
            return

        card = self._card_at(pos.x(), pos.y())
        if card:
            self._dragging_card = card
            self._drag_card_start_x = card.x
            self._drag_card_start_y = card.y
            self._drag_start = pos
            self._original_z_order = list(self._cards)
            self._cards.remove(card)
            self._cards.append(card)
        else:
            self._pan_start = pos

    def mouseMoveEvent(self, event) -> None:
        pos = event.position().toPoint()
        if self._dragging_card is not None and self._drag_start is not None:
            dx = (pos.x() - self._drag_start.x()) / self._pixels_per_unit
            dy = (pos.y() - self._drag_start.y()) / self._pixels_per_unit
            new_x = int(round(self._drag_card_start_x + dx))
            new_y = int(round(self._drag_card_start_y + dy))
            new_x, new_y = self._clamp_position(new_x, new_y)
            self._dragging_card.x = new_x
            self._dragging_card.y = new_y
            self.update()
        elif self._pan_start is not None:
            dx = pos.x() - self._pan_start.x()
            dy = pos.y() - self._pan_start.y()
            self._pan_x -= dx / self._pixels_per_unit
            self._pan_y -= dy / self._pixels_per_unit
            self._pan_start = pos
            self.update()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            super().mouseReleaseEvent(event)
            return

        if self._dragging_card is not None:
            new_x, new_y = self._clamp_position(
                self._dragging_card.x,
                self._dragging_card.y,
            )
            self._dragging_card.x = new_x
            self._dragging_card.y = new_y
            self.cardMoved.emit(self._dragging_card.player_id, new_x, new_y)
            self._cards = list(self._original_z_order)
            self.update()
            self._dragging_card = None
            self._drag_start = None
            self._original_z_order = []

        self._pan_start = None

    def get_add_player_button(self) -> QPushButton:
        """Return the Add Player button for connecting signals."""
        return self._add_player_btn
