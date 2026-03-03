"""
Play history dialog: view, edit, and delete play log entries.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QDialogButtonBox,
    QPushButton,
    QLabel,
    QLineEdit,
    QMessageBox,
    QMenu,
    QStyledItemDelegate,
)
from PySide6.QtCore import Qt, QDateTime, QDate, QTime, QSize
from PySide6.QtWidgets import QDateTimeEdit

from ..services.app_state import AppState
from ..db.play_log import get_play_history, update_play_log_entry, delete_play_log_entry


# Compact row height similar to table entries
_PLAY_HISTORY_ROW_HEIGHT = 30


class _CompactListDelegate(QStyledItemDelegate):
    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        size.setHeight(_PLAY_HISTORY_ROW_HEIGHT)
        return size


def _format_entry(
    played_at_iso: str,
    setlist_name: str | None,
    context_note: str | None,
) -> str:
    try:
        dt = datetime.fromisoformat(played_at_iso.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        local = dt.astimezone()
        when = local.strftime("%Y-%m-%d %H:%M")
    except Exception:
        when = played_at_iso
    parts = [when]
    if setlist_name:
        parts.append(f"Set: {setlist_name}")
    if context_note:
        parts.append(context_note)
    return "  |  ".join(parts)


def open_play_history_dialog(
    app_state: AppState,
    song_id: int,
    song_title: str,
    parent: QDialog | None,
    on_refresh: Callable[[], None] | None = None,
) -> None:
    """
    Open the play history dialog. Users can view, edit, and delete entries.
    on_refresh is called after any edit/delete (e.g. to refresh library table).
    """
    dlg = QDialog(parent)
    dlg.setWindowTitle(f"Play history — {song_title}")
    layout = QVBoxLayout(dlg)
    list_widget = QListWidget(dlg)
    list_widget.setItemDelegate(_CompactListDelegate(list_widget))
    list_widget.setSpacing(0)
    layout.addWidget(list_widget)

    def _refresh_list() -> None:
        list_widget.clear()
        history = get_play_history(app_state.conn, song_id)
        for play_log_id, played_at_iso, setlist_name, context_note in history:
            item = QListWidgetItem(_format_entry(played_at_iso, setlist_name, context_note))
            item.setData(Qt.ItemDataRole.UserRole, (play_log_id, played_at_iso, context_note))
            list_widget.addItem(item)

    def _edit_selected() -> None:
        item = list_widget.currentItem()
        if not item:
            QMessageBox.information(dlg, "Edit", "Select an entry to edit.")
            return
        play_log_id, played_at_iso, context_note = item.data(Qt.ItemDataRole.UserRole)
        edit_dlg = QDialog(dlg)
        edit_dlg.setWindowTitle("Edit play entry")
        edit_layout = QVBoxLayout(edit_dlg)
        dt_edit = QDateTimeEdit(edit_dlg)
        dt_edit.setCalendarPopup(True)
        try:
            dt = datetime.fromisoformat(played_at_iso.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            qdt = QDateTime(
                QDate(dt.year, dt.month, dt.day),
                QTime(dt.hour, dt.minute, dt.second, dt.microsecond // 1000),
            )
            dt_edit.setDateTime(qdt)
        except Exception:
            dt_edit.setDateTime(QDateTime.currentDateTime())
        edit_layout.addWidget(QLabel("Date/Time:"))
        edit_layout.addWidget(dt_edit)
        note_edit = QLineEdit(edit_dlg)
        note_edit.setPlaceholderText("Context note (optional)")
        note_edit.setText(context_note or "")
        edit_layout.addWidget(QLabel("Note:"))
        edit_layout.addWidget(note_edit)
        edit_bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        edit_bb.accepted.connect(edit_dlg.accept)
        edit_bb.rejected.connect(edit_dlg.reject)
        edit_layout.addWidget(edit_bb)
        if edit_dlg.exec() == QDialog.DialogCode.Accepted:
            dt = dt_edit.dateTime().toPython()
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            new_note = note_edit.text().strip() or None
            update_play_log_entry(
                app_state.conn,
                play_log_id,
                played_at_iso=dt.isoformat(),
                context_note=new_note,
            )
            _refresh_list()
            if on_refresh:
                on_refresh()

    def _delete_selected() -> None:
        item = list_widget.currentItem()
        if not item:
            QMessageBox.information(dlg, "Delete", "Select an entry to delete.")
            return
        reply = QMessageBox.question(
            dlg,
            "Delete play entry",
            "Delete this play entry?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            play_log_id, _, _ = item.data(Qt.ItemDataRole.UserRole)
            delete_play_log_entry(app_state.conn, play_log_id)
            _refresh_list()
            if on_refresh:
                on_refresh()

    def _on_context_menu(pos) -> None:
        item = list_widget.itemAt(pos)
        if not item:
            return
        menu = QMenu(dlg)
        menu.addAction("Edit...").triggered.connect(_edit_selected)
        menu.addAction("Delete").triggered.connect(_delete_selected)
        menu.exec(list_widget.viewport().mapToGlobal(pos))

    list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
    list_widget.customContextMenuRequested.connect(_on_context_menu)
    list_widget.itemDoubleClicked.connect(lambda: _edit_selected())

    btn_layout = QHBoxLayout()
    edit_btn = QPushButton("Edit...")
    edit_btn.clicked.connect(_edit_selected)
    delete_btn = QPushButton("Delete")
    delete_btn.clicked.connect(_delete_selected)
    btn_layout.addWidget(edit_btn)
    btn_layout.addWidget(delete_btn)
    btn_layout.addStretch()
    layout.addLayout(btn_layout)

    bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
    bb.accepted.connect(dlg.accept)
    layout.addWidget(bb)

    _refresh_list()
    dlg.resize(520, 360)
    dlg.exec()
