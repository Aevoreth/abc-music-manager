"""
Play history dialog: view, edit, add, and delete play log entries.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QAbstractItemView,
    QDialogButtonBox,
    QPushButton,
    QLabel,
    QLineEdit,
    QMessageBox,
    QMenu,
)
from PySide6.QtCore import Qt, QDateTime, QDate, QTime
from PySide6.QtWidgets import QDateTimeEdit

from ..services.app_state import AppState
from ..db.play_log import (
    get_play_history,
    update_play_log_entry,
    delete_play_log_entry,
    log_play_at,
)


def _format_datetime(played_at_iso: str) -> str:
    try:
        dt = datetime.fromisoformat(played_at_iso.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        local = dt.astimezone()
        return local.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return played_at_iso


def _format_relative_time(played_at_iso: str) -> str:
    try:
        dt = datetime.fromisoformat(played_at_iso.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - dt.astimezone(timezone.utc)
        total_seconds = int(delta.total_seconds())
        if total_seconds < 60:
            return "just now"
        if total_seconds < 3600:
            mins = total_seconds // 60
            return f"{mins} min ago"
        if total_seconds < 86400:
            hours = total_seconds // 3600
            return f"{hours} hour{'s' if hours != 1 else ''} ago"
        if total_seconds < 604800:
            days = total_seconds // 86400
            return f"{days} day{'s' if days != 1 else ''} ago"
        if total_seconds < 2592000:
            weeks = total_seconds // 604800
            return f"{weeks} week{'s' if weeks != 1 else ''} ago"
        if total_seconds < 31536000:
            months = total_seconds // 2592000
            return f"{months} month{'s' if months != 1 else ''} ago"
        years = total_seconds // 31536000
        return f"{years} year{'s' if years != 1 else ''} ago"
    except Exception:
        return ""


def _run_edit_add_dialog(
    parent: QDialog,
    title: str,
    initial_datetime: datetime,
    initial_note: str,
    on_accept: Callable[[datetime, str | None], None],
) -> bool:
    """Show date/time + note dialog. on_accept(dt, note) called if user clicks OK. Returns True if accepted."""
    edit_dlg = QDialog(parent)
    edit_dlg.setWindowTitle(title)
    edit_layout = QVBoxLayout(edit_dlg)
    dt_edit = QDateTimeEdit(edit_dlg)
    dt_edit.setCalendarPopup(True)
    qdt = QDateTime(
        QDate(initial_datetime.year, initial_datetime.month, initial_datetime.day),
        QTime(initial_datetime.hour, initial_datetime.minute, initial_datetime.second, initial_datetime.microsecond // 1000),
    )
    dt_edit.setDateTime(qdt)
    edit_layout.addWidget(QLabel("Date/Time:"))
    edit_layout.addWidget(dt_edit)
    note_edit = QLineEdit(edit_dlg)
    note_edit.setPlaceholderText("Context note (optional)")
    note_edit.setText(initial_note or "")
    edit_layout.addWidget(QLabel("Note:"))
    edit_layout.addWidget(note_edit)
    edit_bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
    edit_bb.accepted.connect(edit_dlg.accept)
    edit_bb.rejected.connect(edit_dlg.reject)
    edit_layout.addWidget(edit_bb)
    if edit_dlg.exec() == QDialog.DialogCode.Accepted:
        dt = dt_edit.dateTime().toPython()
        if dt.tzinfo is None:
            # QDateTimeEdit returns naive local time; interpret as local and convert to UTC
            dt = dt.replace(tzinfo=datetime.now().astimezone().tzinfo).astimezone(timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        new_note = note_edit.text().strip() or None
        on_accept(dt, new_note)
        return True
    return False


def open_play_history_dialog(
    app_state: AppState,
    song_id: int,
    song_title: str,
    parent: QDialog | None,
    on_refresh: Callable[[], None] | None = None,
) -> None:
    """
    Open the play history dialog. Users can view, add, edit, and delete entries.
    on_refresh is called after any add/edit/delete (e.g. to refresh library table).
    """
    dlg = QDialog(parent)
    dlg.setWindowTitle(f"Play history — {song_title}")
    layout = QVBoxLayout(dlg)
    table = QTableWidget(dlg)
    table.setColumnCount(2)
    table.setHorizontalHeaderLabels(["Date/time", "Relative time"])
    table.horizontalHeader().setStretchLastSection(True)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    table.setAlternatingRowColors(True)
    table.verticalHeader().setVisible(False)
    layout.addWidget(table)

    def _refresh_table() -> None:
        table.setRowCount(0)
        history = get_play_history(app_state.conn, song_id)
        for play_log_id, played_at_iso, _setlist_name, context_note in history:
            row = table.rowCount()
            table.insertRow(row)
            dt_item = QTableWidgetItem(_format_datetime(played_at_iso))
            dt_item.setData(Qt.ItemDataRole.UserRole, (play_log_id, played_at_iso, context_note))
            table.setItem(row, 0, dt_item)
            table.setItem(row, 1, QTableWidgetItem(_format_relative_time(played_at_iso)))

    def _get_selected_row_data() -> tuple[int, str, str | None] | None:
        row = table.currentRow()
        if row < 0:
            return None
        item = table.item(row, 0)
        if not item:
            return None
        data = item.data(Qt.ItemDataRole.UserRole)
        if not data:
            return None
        return data  # (play_log_id, played_at_iso, context_note)

    def _edit_selected() -> None:
        data = _get_selected_row_data()
        if not data:
            QMessageBox.information(dlg, "Edit", "Select an entry to edit.")
            return
        play_log_id, played_at_iso, context_note = data
        try:
            dt = datetime.fromisoformat(played_at_iso.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
        except Exception:
            dt = datetime.now(timezone.utc)

        def on_accept(edit_dt: datetime, note: str | None) -> None:
            update_play_log_entry(
                app_state.conn,
                play_log_id,
                played_at_iso=edit_dt.isoformat(),
                context_note=note,
            )
            _refresh_table()
            if on_refresh:
                on_refresh()

        _run_edit_add_dialog(
            dlg,
            "Edit play entry",
            dt.astimezone(),  # Convert to local for display
            context_note or "",
            on_accept,
        )

    def _delete_selected() -> None:
        data = _get_selected_row_data()
        if not data:
            QMessageBox.information(dlg, "Delete", "Select an entry to delete.")
            return
        play_log_id, _, _ = data
        reply = QMessageBox.question(
            dlg,
            "Delete play entry",
            "Delete this play entry?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            delete_play_log_entry(app_state.conn, play_log_id)
            _refresh_table()
            if on_refresh:
                on_refresh()

    def _add_entry() -> None:
        now = datetime.now().astimezone()  # Local time for display

        def on_accept(add_dt: datetime, note: str | None) -> None:
            log_play_at(app_state.conn, song_id, add_dt.isoformat(), context_note=note)
            _refresh_table()
            if on_refresh:
                on_refresh()

        _run_edit_add_dialog(
            dlg,
            "Add play entry",
            now,
            "",
            on_accept,
        )

    def _on_context_menu(pos) -> None:
        index = table.indexAt(pos)
        if not index.isValid():
            return
        table.setCurrentCell(index.row(), 0)
        menu = QMenu(dlg)
        menu.addAction("Edit...").triggered.connect(_edit_selected)
        menu.addAction("Delete").triggered.connect(_delete_selected)
        menu.exec(table.viewport().mapToGlobal(pos))

    table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
    table.customContextMenuRequested.connect(_on_context_menu)

    def _on_double_click(row: int, _col: int) -> None:
        table.setCurrentCell(row, 0)
        _edit_selected()

    table.cellDoubleClicked.connect(_on_double_click)

    btn_layout = QHBoxLayout()
    add_btn = QPushButton("Add...")
    add_btn.clicked.connect(_add_entry)
    edit_btn = QPushButton("Edit...")
    edit_btn.clicked.connect(_edit_selected)
    delete_btn = QPushButton("Delete")
    delete_btn.clicked.connect(_delete_selected)
    btn_layout.addWidget(add_btn)
    btn_layout.addWidget(edit_btn)
    btn_layout.addWidget(delete_btn)
    btn_layout.addStretch()
    layout.addLayout(btn_layout)

    bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
    bb.accepted.connect(dlg.accept)
    layout.addWidget(bb)

    _refresh_table()
    dlg.resize(520, 360)
    dlg.exec()
