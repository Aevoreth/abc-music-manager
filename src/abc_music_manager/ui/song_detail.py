"""
Song Detail / Edit: metadata display, app-only editing, optional raw ABC editing with conflict handling.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QComboBox,
    QPushButton,
    QTabWidget,
    QWidget,
    QFormLayout,
    QMessageBox,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QStyledItemDelegate,
    QStyleOptionViewItem,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QBrush

from ..services.app_state import AppState
from ..db import get_song_for_detail
from ..db.library_query import get_primary_file_path_for_song
from ..db.band_repo import get_band_layout_display_name
from ..db.status_repo import list_statuses
from ..db.song_layout_repo import (
    list_song_layouts_for_song,
    delete_song_layout,
)
from ..db.song_repo import update_song_app_metadata, ensure_song_from_parsed
from ..db.play_log import log_play
from .play_history_dialog import open_play_history_dialog
from .song_layout_editor_dialog import SongLayoutEditorDialog
from .library_view import RatingComboBox, RatingComboDelegate, _rating_label
from .theme import STATUS_CIRCLE_DIAMETER, COLOR_OUTLINE_VARIANT
from ..parsing import parse_abc_content
from ..scanning.scanner import _file_mtime_str, _file_hash


def _format_duration(sec: int | None) -> str:
    if sec is None:
        return "—"
    m, s = divmod(sec, 60)
    return f"{m}:{s:02d}"


def _format_play_datetime(played_at_iso: str) -> str:
    """Format as local 'YYYY-MM-DD - HH:MM' (no T)."""
    try:
        dt = datetime.fromisoformat(played_at_iso.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        local = dt.astimezone()
        return local.strftime("%Y-%m-%d - %H:%M")
    except Exception:
        return played_at_iso or "—"


def _format_play_relative(played_at_iso: str) -> str:
    """Format as relative time, e.g. '2h ago', '1d ago'."""
    try:
        dt = datetime.fromisoformat(played_at_iso.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        delta = now - dt.astimezone(timezone.utc)
        total_seconds = int(delta.total_seconds())
        if total_seconds < 60:
            return "just now"
        if total_seconds < 3600:
            return f"{total_seconds // 60}m ago"
        if total_seconds < 86400:
            return f"{total_seconds // 3600}h ago"
        if total_seconds < 604800:
            return f"{total_seconds // 86400}d ago"
        if total_seconds < 2592000:
            return f"{total_seconds // 604800}w ago"
        if total_seconds < 31536000:
            return f"{total_seconds // 2592000}mo ago"
        return f"{total_seconds // 31536000}y ago"
    except Exception:
        return ""


class StatusComboDelegate(QStyledItemDelegate):
    """Paints song detail status combo items with colored circle + name (like status filter)."""

    def __init__(self, status_colors: dict[int, str | None], parent=None):
        super().__init__(parent)
        self._status_colors = status_colors

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index) -> None:
        text = index.data(Qt.ItemDataRole.DisplayRole) or ""
        status_id = index.data(Qt.ItemDataRole.UserRole)
        opt = QStyleOptionViewItem(option)
        rect = opt.rect.adjusted(2, 0, -2, 0)
        if status_id is None or status_id == -1:
            painter.drawText(rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, text)
            return
        try:
            color = self._status_colors.get(status_id) or COLOR_OUTLINE_VARIANT
            qcolor = QColor(color)
        except Exception:
            qcolor = QColor(COLOR_OUTLINE_VARIANT)
        painter.setBrush(QBrush(qcolor))
        painter.setPen(Qt.PenStyle.NoPen)
        cy = rect.center().y()
        r = STATUS_CIRCLE_DIAMETER // 2
        painter.drawEllipse(rect.x(), cy - r, STATUS_CIRCLE_DIAMETER, STATUS_CIRCLE_DIAMETER)
        painter.setPen(QPen(opt.palette.color(opt.palette.currentColorGroup(), opt.palette.ColorRole.Text)))
        painter.drawText(rect.adjusted(STATUS_CIRCLE_DIAMETER + 4, 0, 0, 0), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, text)


class SongDetailDialog(QDialog):
    """View and edit song metadata; optional raw ABC tab with conflict handling."""

    song_layout_updated = Signal(int)  # song_layout_id

    def __init__(self, app_state: AppState, song_id: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.app_state = app_state
        self.song_id = song_id
        self._file_path: str | None = None
        self._file_mtime_when_loaded: str | None = None
        self.setWindowTitle("Song detail")
        self.setMinimumSize(620, 520)
        layout = QVBoxLayout(self)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_basic_info_tab(), "Basic Info")
        self.tabs.addTab(self._build_parts_tab(), "Parts list and Layouts")
        self.tabs.addTab(self._build_notes_lyrics_tab(), "Notes and Lyrics")
        self.tabs.addTab(self._build_abc_tab(), "Raw ABC")
        layout.addWidget(self.tabs)

        btn_layout = QHBoxLayout()
        save_metadata_to_abc_btn = QPushButton("Save Metadata to ABC")
        save_metadata_to_abc_btn.setEnabled(False)
        save_metadata_to_abc_btn.setToolTip("Not yet implemented")
        btn_layout.addWidget(save_metadata_to_abc_btn)
        btn_layout.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self._save_app_metadata)
        btn_layout.addWidget(save_btn)
        layout.addLayout(btn_layout)

        self._load_song()

    def _build_basic_info_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        self.title_label = QLabel()
        self.composers_label = QLabel()
        self.transcriber_label = QLabel()
        self.duration_label = QLabel()
        self.export_ts_label = QLabel()
        self.parts_label = QLabel()
        form.addRow("Title:", self.title_label)
        form.addRow("Composer(s):", self.composers_label)
        form.addRow("Transcriber:", self.transcriber_label)
        form.addRow("Duration:", self.duration_label)
        form.addRow("Export timestamp:", self.export_ts_label)
        form.addRow("Part count:", self.parts_label)

        self.rating_combo = RatingComboBox()
        self.rating_combo.setItemDelegate(RatingComboDelegate(self.rating_combo))
        for i in range(6):
            self.rating_combo.addItem(_rating_label(i), i)
        self.rating_combo.setMinimumWidth(0)
        self.rating_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        form.addRow("Rating:", self.rating_combo)
        self.status_combo = QComboBox()
        self.status_combo.setObjectName("song_detail_status_combo")
        self.status_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        form.addRow("Status:", self.status_combo)
        self.play_history_label = QLabel()
        self.play_history_label.setWordWrap(True)
        self.play_history_label.setFixedHeight(self.play_history_label.fontMetrics().lineSpacing() * 4)
        form.addRow("Play history:", self.play_history_label)
        history_btn_layout = QHBoxLayout()
        mark_played_btn = QPushButton("Mark as played now")
        mark_played_btn.clicked.connect(self._mark_played)
        edit_history_btn = QPushButton("Edit play history...")
        edit_history_btn.clicked.connect(self._edit_play_history)
        history_btn_layout.addWidget(mark_played_btn)
        history_btn_layout.addWidget(edit_history_btn)
        history_btn_layout.addStretch()
        form.addRow("", history_btn_layout)
        return w

    def _build_parts_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        self.parts_table = QTableWidget()
        self._setup_parts_table(self.parts_table)
        layout.addWidget(self.parts_table)

        layout.addWidget(QLabel("Layouts (band-specific song layouts):"))
        layout_row = QHBoxLayout()
        self.layout_combo = QComboBox()
        self.layout_combo.setMinimumWidth(200)
        self.layout_combo.currentIndexChanged.connect(self._on_layout_combo_changed)
        layout_row.addWidget(self.layout_combo)
        new_layout_btn = QPushButton("New song layout")
        new_layout_btn.clicked.connect(self._on_new_layout)
        layout_row.addWidget(new_layout_btn)
        self.edit_layout_btn = QPushButton("Edit song layout")
        self.edit_layout_btn.clicked.connect(self._on_edit_layout)
        layout_row.addWidget(self.edit_layout_btn)
        self.delete_layout_btn = QPushButton("Delete song layout")
        self.delete_layout_btn.clicked.connect(self._on_delete_layout)
        layout_row.addWidget(self.delete_layout_btn)
        layout_row.addStretch()
        layout.addLayout(layout_row)
        return w

    def _setup_parts_table(self, table: QTableWidget) -> None:
        table.setColumnCount(3)
        table.setHorizontalHeaderLabels(["Part #", "Made For", "Part Name"])
        for i in range(3):
            table.horizontalHeader().setSectionResizeMode(i, QHeaderView.ResizeMode.Interactive)
        table.setAlternatingRowColors(True)
        fm = table.fontMetrics()
        table.verticalHeader().setDefaultSectionSize(fm.lineSpacing() + 4)
        table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)

    def _build_notes_lyrics_tab(self) -> QWidget:
        w = QWidget()
        main = QVBoxLayout(w)
        cols = QHBoxLayout()
        notes_col = QVBoxLayout()
        notes_col.addWidget(QLabel("Notes:"))
        self.notes_edit = QPlainTextEdit()
        self.notes_edit.setPlaceholderText("Your notes...")
        notes_col.addWidget(self.notes_edit)
        cols.addLayout(notes_col)
        lyrics_col = QVBoxLayout()
        lyrics_col.addWidget(QLabel("Lyrics:"))
        self.lyrics_edit = QPlainTextEdit()
        self.lyrics_edit.setPlaceholderText("Lyrics...")
        lyrics_col.addWidget(self.lyrics_edit)
        cols.addLayout(lyrics_col)
        main.addLayout(cols)
        return w

    def _build_abc_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        self.abc_edit = QPlainTextEdit()
        self.abc_edit.setPlaceholderText("No primary file for this song, or file not found.")
        layout.addWidget(self.abc_edit)
        btn_layout = QHBoxLayout()
        save_abc_btn = QPushButton("Save to file")
        save_abc_btn.clicked.connect(self._save_abc)
        reload_btn = QPushButton("Reload from file")
        reload_btn.clicked.connect(self._reload_abc)
        btn_layout.addWidget(save_abc_btn)
        btn_layout.addWidget(reload_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)
        return w

    def _load_song(self) -> None:
        data = get_song_for_detail(self.app_state.conn, self.song_id)
        if not data:
            self.title_label.setText("(not found)")
            self._parts_json = "[]"
            self._layouts_list = []
            return
        self.title_label.setText(data["title"])
        self.composers_label.setText(data["composers"])
        self.transcriber_label.setText(data.get("transcriber") or "—")
        self.duration_label.setText(_format_duration(data.get("duration_seconds")))
        self.export_ts_label.setText(data.get("export_timestamp") or "—")
        self.parts_label.setText(str(data.get("part_count", 0)))

        parts = data.get("parts") or []
        self._parts_json = json.dumps(parts)
        self._layouts_list = list_song_layouts_for_song(self.app_state.conn, self.song_id)
        self._fill_parts_table(self.parts_table, parts)
        self.layout_combo.clear()
        self.layout_combo.addItem("(none)", None)
        for sl, _ in self._layouts_list:
            label = get_band_layout_display_name(self.app_state.conn, sl.band_layout_id)
            self.layout_combo.addItem(label, (sl.id, sl.band_layout_id))
        self.layout_combo.setCurrentIndex(0)
        self._on_layout_combo_changed()

        rating = data.get("rating")
        idx = int(rating) if rating is not None else 0
        self.rating_combo.setCurrentIndex(min(idx, 5))
        self.notes_edit.setPlainText(data.get("notes") or "")
        self.lyrics_edit.setPlainText(data.get("lyrics") or "")

        statuses = list_statuses(self.app_state.conn)
        status_colors = {r.id: r.color for r in statuses}
        self.status_combo.clear()
        self.status_combo.setItemDelegate(StatusComboDelegate(status_colors, self.status_combo))
        self.status_combo.addItem("(none)", -1)
        for r in statuses:
            self.status_combo.addItem(r.name, r.id)
        status_id = data.get("status_id")
        for i in range(self.status_combo.count()):
            if self.status_combo.itemData(i) == status_id:
                self.status_combo.setCurrentIndex(i)
                break
        else:
            self.status_combo.setCurrentIndex(0)

        self._file_path = get_primary_file_path_for_song(self.app_state.conn, self.song_id)
        self._load_play_history()
        self._load_abc_content()

    def _fill_parts_table(self, table: QTableWidget, parts: list) -> None:
        table.setRowCount(len(parts))
        for i, p in enumerate(parts):
            table.setItem(i, 0, QTableWidgetItem(str(p.get("part_number", i + 1))))
            table.setItem(i, 1, QTableWidgetItem(p.get("instrument_name") or "—"))
            table.setItem(i, 2, QTableWidgetItem(p.get("part_name") or "—"))
        table.resizeColumnsToContents()
        for col in range(3):
            table.setColumnWidth(col, table.columnWidth(col) + 10)

    def _on_layout_combo_changed(self) -> None:
        has_layout = self.layout_combo.currentData() is not None
        self.edit_layout_btn.setEnabled(has_layout)
        self.delete_layout_btn.setEnabled(has_layout)

    def _on_new_layout(self) -> None:
        dlg = SongLayoutEditorDialog(
            self.app_state,
            self.song_id,
            getattr(self, "_parts_json", "[]"),
            song_layout_id=None,
            band_layout_id=None,
            parent=self,
        )
        dlg.song_layout_updated.connect(self.song_layout_updated.emit)
        if dlg.exec():
            self._load_song()

    def _on_edit_layout(self) -> None:
        data = self.layout_combo.currentData()
        if not data:
            return
        song_layout_id, band_layout_id = data
        dlg = SongLayoutEditorDialog(
            self.app_state,
            self.song_id,
            getattr(self, "_parts_json", "[]"),
            song_layout_id=song_layout_id,
            band_layout_id=band_layout_id,
            parent=self,
        )
        dlg.song_layout_updated.connect(self.song_layout_updated.emit)
        if dlg.exec():
            self._load_song()

    def _on_delete_layout(self) -> None:
        data = self.layout_combo.currentData()
        if not data:
            return
        song_layout_id, _ = data
        reply = QMessageBox.question(
            self,
            "Delete song layout",
            "Delete this song layout? Setlist copies are independent and will not be affected.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            delete_song_layout(self.app_state.conn, song_layout_id)
            self._load_song()

    def _load_play_history(self) -> None:
        cur = self.app_state.conn.execute(
            "SELECT played_at, context_note FROM PlayLog WHERE song_id = ? ORDER BY played_at DESC",
            (self.song_id,),
        )
        rows = cur.fetchall()
        if not rows:
            self.play_history_label.setText("No plays recorded.")
            return
        lines = []
        for played_at, note in rows[:3]:
            dt_str = _format_play_datetime(played_at or "")
            rel_str = _format_play_relative(played_at or "")
            line = f"{dt_str} ({rel_str})"
            if note and note.strip():
                line += f" — {note.strip()}"
            lines.append(line)
        if len(rows) > 3:
            lines.append(f"{len(rows)} plays total")
        self.play_history_label.setText("\n".join(lines))

    def _mark_played(self) -> None:
        log_play(self.app_state.conn, self.song_id)
        self._load_song()
        self._load_play_history()

    def _edit_play_history(self) -> None:
        data = get_song_for_detail(self.app_state.conn, self.song_id)
        title = data["title"] if data else "Song"
        open_play_history_dialog(
            self.app_state,
            self.song_id,
            title,
            self,
            on_refresh=self._load_song,
        )

    def _load_abc_content(self) -> None:
        self.abc_edit.clear()
        if not self._file_path or not Path(self._file_path).is_file():
            return
        try:
            content = Path(self._file_path).read_text(encoding="utf-8", errors="replace")
            self.abc_edit.setPlainText(content)
            self._file_mtime_when_loaded = _file_mtime_str(Path(self._file_path))
        except Exception as e:
            self.abc_edit.setPlainText(f"# Error reading file: {e}")

    def _reload_abc(self) -> None:
        self._load_abc_content()
        if self._file_path:
            self._file_mtime_when_loaded = _file_mtime_str(Path(self._file_path))

    def _save_app_metadata(self) -> None:
        rating_val = self.rating_combo.currentData()
        rating = None if rating_val is None or rating_val == 0 else int(rating_val)
        status_id = self.status_combo.currentData()
        if status_id == -1:
            status_id = None
        notes = self.notes_edit.toPlainText().strip()
        lyrics = self.lyrics_edit.toPlainText().strip()
        update_song_app_metadata(
            self.app_state.conn,
            self.song_id,
            rating=rating,
            status_id=status_id,
            notes=notes,
            lyrics=lyrics,
        )
        self.accept()

    def _save_abc(self) -> None:
        if not self._file_path:
            QMessageBox.warning(self, "No file", "No primary file path for this song.")
            return
        path = Path(self._file_path)
        current_mtime = _file_mtime_str(path)
        if current_mtime != self._file_mtime_when_loaded:
            reply = QMessageBox.question(
                self,
                "File changed",
                "The file was modified on disk. Overwrite anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Cancel:
                return
            if reply == QMessageBox.StandardButton.No:
                self._load_abc_content()
                return
        try:
            content = self.abc_edit.toPlainText()
            path.write_text(content, encoding="utf-8")
            parsed = parse_abc_content(content, filename=path.name)
            ensure_song_from_parsed(
                self.app_state.conn,
                parsed,
                str(path.resolve()),
                file_mtime=current_mtime or _file_mtime_str(path),
                file_hash=_file_hash(path),
                is_primary_library=True,
                is_set_copy=False,
                scan_excluded=False,
            )
            self._file_mtime_when_loaded = _file_mtime_str(path)
            self._load_song()
            QMessageBox.information(self, "Saved", "File saved and re-parsed.")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
