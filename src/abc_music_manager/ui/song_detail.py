"""
Song Detail / Edit: metadata display, app-only editing, optional raw ABC editing with conflict handling.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QComboBox,
    QSpinBox,
    QPushButton,
    QTabWidget,
    QWidget,
    QFormLayout,
    QMessageBox,
    QFileDialog,
)
from PySide6.QtCore import Qt

from ..services.app_state import AppState
from ..db import get_song_for_detail, get_status_list
from ..db.library_query import get_primary_file_path_for_song
from ..db.song_repo import update_song_app_metadata, ensure_song_from_parsed
from ..db.play_log import log_play
from ..parsing import parse_abc_content
from ..scanning.scanner import _file_mtime_str, _file_hash


def _format_duration(sec: int | None) -> str:
    if sec is None:
        return "—"
    m, s = divmod(sec, 60)
    return f"{m}:{s:02d}"


class SongDetailDialog(QDialog):
    """View and edit song metadata; optional raw ABC tab with conflict handling."""

    def __init__(self, app_state: AppState, song_id: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.app_state = app_state
        self.song_id = song_id
        self._file_path: str | None = None
        self._file_mtime_when_loaded: str | None = None
        self.setWindowTitle("Song detail")
        self.setMinimumSize(500, 450)
        layout = QVBoxLayout(self)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_info_tab(), "Info")
        self.tabs.addTab(self._build_abc_tab(), "Raw ABC")
        layout.addWidget(self.tabs)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignRight)

        self._load_song()

    def _build_info_tab(self) -> QWidget:
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
        self.parts_text = QLabel()
        self.parts_text.setWordWrap(True)
        form.addRow("Parts:", self.parts_text)

        form.addRow("Rating (0–5):", QLabel())  # spacer
        self.rating_spin = QSpinBox()
        self.rating_spin.setRange(0, 5)
        self.rating_spin.setSpecialValueText("—")
        form.addRow("", self.rating_spin)
        self.status_combo = QComboBox()
        self.status_combo.addItem("(none)", None)
        form.addRow("Status:", self.status_combo)
        self.notes_edit = QPlainTextEdit()
        self.notes_edit.setMaximumHeight(80)
        form.addRow("Notes:", self.notes_edit)
        self.lyrics_edit = QPlainTextEdit()
        self.lyrics_edit.setMaximumHeight(100)
        form.addRow("Lyrics:", self.lyrics_edit)
        save_btn = QPushButton("Save app metadata")
        save_btn.clicked.connect(self._save_app_metadata)
        form.addRow("", save_btn)
        form.addRow("Play history:", QLabel())
        self.play_history_label = QLabel()
        self.play_history_label.setWordWrap(True)
        form.addRow("", self.play_history_label)
        mark_played_btn = QPushButton("Mark as played now")
        mark_played_btn.clicked.connect(self._mark_played)
        form.addRow("", mark_played_btn)
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
            return
        self.title_label.setText(data["title"])
        self.composers_label.setText(data["composers"])
        self.transcriber_label.setText(data.get("transcriber") or "—")
        self.duration_label.setText(_format_duration(data.get("duration_seconds")))
        self.export_ts_label.setText(data.get("export_timestamp") or "—")
        self.parts_label.setText(str(data.get("part_count", 0)))
        parts = data.get("parts") or []
        parts_str = "\n".join(
            f"  Part {p.get('part_number')}: {p.get('part_name') or '—'} (made for: {p.get('instrument_name') or '—'})"
            for p in parts
        )
        self.parts_text.setText(parts_str or "—")

        self.rating_spin.setValue(data["rating"] if data.get("rating") is not None else 0)
        self.notes_edit.setPlainText(data.get("notes") or "")
        self.lyrics_edit.setPlainText(data.get("lyrics") or "")

        self.status_combo.clear()
        self.status_combo.addItem("(none)", -1)
        for sid, name in get_status_list(self.app_state.conn):
            self.status_combo.addItem(name, sid)
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

    def _load_play_history(self) -> None:
        cur = self.app_state.conn.execute(
            "SELECT played_at, context_note FROM PlayLog WHERE song_id = ? ORDER BY played_at DESC LIMIT 20",
            (self.song_id,),
        )
        rows = cur.fetchall()
        if not rows:
            self.play_history_label.setText("No plays recorded.")
            return
        lines = []
        for played_at, note in rows:
            line = played_at[:19] if played_at and len(played_at) >= 19 else str(played_at)
            if note and note.strip():
                line += f" — {note.strip()}"
            lines.append(line)
        self.play_history_label.setText("\n".join(lines))

    def _mark_played(self) -> None:
        log_play(self.app_state.conn, self.song_id)
        self._load_song()
        self._load_play_history()
        QMessageBox.information(self, "Play logged", "Play recorded.")

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
        rating = self.rating_spin.value()
        if self.rating_spin.specialValueText() == "—" and rating == 0:
            rating = None
        else:
            rating = rating if rating else None
        status_id = self.status_combo.currentData()
        if status_id == -1:
            status_id = None
        notes = self.notes_edit.toPlainText().strip() or None
        lyrics = self.lyrics_edit.toPlainText().strip() or None
        update_song_app_metadata(
            self.app_state.conn,
            self.song_id,
            rating=rating,
            status_id=status_id,
            notes=notes,
            lyrics=lyrics,
        )
        QMessageBox.information(self, "Saved", "App metadata saved.")

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
