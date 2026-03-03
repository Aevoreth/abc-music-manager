"""
Dialog showing verbose PluginData export progress with errors highlighted in red.
"""

from __future__ import annotations

import sqlite3

from PySide6.QtCore import QTimer
from PySide6.QtGui import QColor, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from ..services.plugindata_writer import write_plugindata_all_targets


class PlugindataExportDialog(QDialog):
    """Modal dialog that runs PluginData export and shows verbose output with errors in red."""

    def __init__(self, conn: sqlite3.Connection, parent=None) -> None:
        super().__init__(parent)
        self.conn = conn
        self._export_started = False
        self.setWindowTitle("PluginData Export")
        self.setMinimumSize(520, 360)
        self.resize(600, 420)

        layout = QVBoxLayout(self)
        self.log_edit = QTextEdit()
        self.log_edit.setReadOnly(True)
        self.log_edit.setStyleSheet("font-family: monospace; font-size: 12px;")
        layout.addWidget(self.log_edit)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.close_btn = QPushButton("Close")
        self.close_btn.setEnabled(False)
        self.close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(self.close_btn)
        layout.addLayout(btn_layout)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self._export_started:
            self._export_started = True
            QTimer.singleShot(0, self._run_export)

    def _append_log(self, text: str, is_error: bool = False) -> None:
        cursor = self.log_edit.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        fmt = QTextCharFormat()
        if is_error:
            fmt.setForeground(QColor("#c0392b"))
        cursor.insertText(text + "\n", fmt)
        self.log_edit.setTextCursor(cursor)
        self.log_edit.ensureCursorVisible()

    def _run_export(self) -> None:
        def log_fn(msg: str, is_error: bool = False) -> None:
            self._append_log(msg, is_error)
            QApplication.processEvents()

        try:
            self._append_log("PluginData Export")
            self._append_log("=" * 40)
            write_plugindata_all_targets(self.conn, log_fn=log_fn)
        except Exception as e:
            self._append_log(str(e), is_error=True)
        finally:
            self.close_btn.setEnabled(True)
