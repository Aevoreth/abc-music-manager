"""
Diagonal/rotated header for QTableWidget to save horizontal space on instrument columns.
"""

from __future__ import annotations

from math import sqrt

from PySide6.QtWidgets import QHeaderView, QStyleOptionHeader, QStyle
from PySide6.QtCore import Qt, QRect, QSize, QRectF
from PySide6.QtGui import QPainter, QFontMetrics, QPaintEvent


class DiagonalHeaderView(QHeaderView):
    """
    Horizontal header that paints specified columns with text rotated -45 degrees.
    Other columns use default painting.
    Text is bottom- and left-justified, painted in a final pass so it is not cut off
    by adjacent section backgrounds.
    """

    def __init__(
        self,
        parent=None,
        *,
        diagonal_start: int = 0,
        diagonal_end: int = -1,
    ) -> None:
        super().__init__(Qt.Orientation.Horizontal, parent)
        self._diagonal_start = diagonal_start
        self._diagonal_end = diagonal_end

    def paintSection(self, painter: QPainter, rect: QRect, logical_index: int) -> None:
        use_diagonal = (
            logical_index >= self._diagonal_start
            and (self._diagonal_end < 0 or logical_index <= self._diagonal_end)
        )
        if use_diagonal:
            # Paint background only; text is drawn in paintEvent's final pass
            opt = QStyleOptionHeader()
            self.initStyleOption(opt)
            opt.rect = rect
            opt.section = logical_index
            opt.textAlignment = Qt.AlignmentFlag.AlignCenter
            opt.text = ""
            self.style().drawControl(QStyle.ControlElement.CE_Header, opt, painter, self)
        else:
            # Non-diagonal (Name, Level, Class, Actions): paint background, then text at bottom
            opt = QStyleOptionHeader()
            self.initStyleOption(opt)
            self.initStyleOptionForIndex(opt, logical_index)
            opt.rect = rect
            opt.section = logical_index
            opt.text = ""
            self.style().drawControl(QStyle.ControlElement.CE_Header, opt, painter, self)
            text = self.model().headerData(
                logical_index, self.orientation(), Qt.ItemDataRole.DisplayRole
            )
            if text:
                painter.save()
                painter.setFont(self.font())
                # Inset rect from bottom so text sits higher (padded up ~8px)
                text_rect = rect.adjusted(0, 0, 0, -8)
                painter.drawText(
                    text_rect,
                    Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter,
                    str(text),
                )
                painter.restore()

    def paintEvent(self, event: QPaintEvent) -> None:
        super().paintEvent(event)
        # Second pass: paint all diagonal text on top so it is not cut off
        # by adjacent section backgrounds, and is not clipped to column width
        if self._diagonal_end < self._diagonal_start or not self.model():
            return
        painter = QPainter(self.viewport())
        painter.setFont(self.font())
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        fm = painter.fontMetrics()
        vp = self.viewport()
        height = vp.height() if vp else self.height()
        for logical in range(self._diagonal_start, self._diagonal_end + 1):
            if self.isSectionHidden(logical):
                continue
            text = self.model().headerData(
                logical, self.orientation(), Qt.ItemDataRole.DisplayRole
            )
            if not text:
                continue
            text = str(text)
            x = self.sectionViewportPosition(logical)
            width = self.sectionSize(logical)
            rect = QRect(x, 0, width, height)
            painter.save()
            painter.setClipping(False)
            # Position at bottom-center of cell, padded up 5px; rotate -45°; text starts at center
            painter.translate(rect.center().x(), rect.bottom() - 5)
            painter.rotate(-45)
            # Text rect: extends up-right from origin; AlignBottom puts text bottom at y=0
            tw = fm.horizontalAdvance(text)
            th = fm.height()
            text_rect = QRectF(0, -th, tw + 4, th)
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignLeft, text)
            painter.restore()
        painter.end()

    def sizeHint(self) -> QSize:
        s = super().sizeHint()
        if self._diagonal_end >= self._diagonal_start and self.model():
            # Diagonal text at -45° needs height = (text_width + text_height) / sqrt(2)
            # Compute for longest header in diagonal range
            fm = QFontMetrics(self.font())
            max_diag = 0
            for i in range(self._diagonal_start, self._diagonal_end + 1):
                text = self.model().headerData(
                    i, self.orientation(), Qt.ItemDataRole.DisplayRole
                )
                if text:
                    tw = fm.horizontalAdvance(str(text))
                    th = fm.height()
                    diag = (tw + th) / sqrt(2)
                    max_diag = max(max_diag, diag)
            min_h = int(max_diag) + 12 if max_diag else 100
            return QSize(s.width(), max(s.height(), min_h))
        return s
