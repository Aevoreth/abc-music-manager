#!/usr/bin/env python3
"""One-off: render checkmark.svg to checkmark.png for QSS (Qt does not show SVG in QCheckBox::indicator)."""
from pathlib import Path

from PySide6.QtCore import QByteArray
from PySide6.QtGui import QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

_here = Path(__file__).resolve().parent
svg_path = _here / "checkmark.svg"
png_path = _here / "checkmark.png"
size = 16

renderer = QSvgRenderer(QByteArray(svg_path.read_bytes()))
img = QImage(size, size, QImage.Format.Format_ARGB32)
img.fill(0)
painter = QPainter(img)
renderer.render(painter)
painter.end()
img.save(str(png_path))
print(f"Wrote {png_path}")
