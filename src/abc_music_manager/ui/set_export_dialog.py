"""
Set export dialog: configure and run export of setlist ABC files to folder/zip.
"""

from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QDragEnterEvent, QDragLeaveEvent, QDragMoveEvent, QDropEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
    QFrame,
)

from ..db.band_repo import list_layout_slots_for_export
from ..db.player_repo import list_players
from ..db.setlist_repo import list_setlist_items_with_song_meta
from ..services.filename_template import (
    SPACE_REPLACE_CHARS,
    SPACE_REPLACE_LABELS,
    format_filename,
)
from ..services.preferences import (
    get_set_export_dir,
    get_set_export_prefs,
    save_set_export_prefs,
)
from ..db.schema import get_db_path
from .theme import COLOR_PRIMARY
from ..services.set_export_service import (
    CSV_AVAILABLE_COLUMNS,
    CSV_DEFAULT_ENABLED,
    SetExportSettings,
    export_set,
)


def _sanitize_set_name(s: str) -> str:
    invalid = re.compile(r'[<>:"/\\|?*]')
    return invalid.sub("", s).strip() or "Untitled Set"


class PlayerOrderListWidget(QListWidget):
    """List widget with orange drop indicator line during drag."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("player_order_list")
        self.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        self._drop_line = QFrame(self.viewport())
        self._drop_line.setFixedHeight(3)
        self._drop_line.setStyleSheet(f"background-color: {COLOR_PRIMARY}; border: none;")
        self._drop_line.hide()

    def _drop_line_y(self, pos) -> int | None:
        """Return y position for drop line, or None to hide."""
        idx = self.indexAt(pos)
        if idx.isValid():
            rect = self.visualRect(idx)
            if pos.y() > rect.center().y():
                return rect.bottom()
            return rect.top()
        if self.count() > 0:
            last = self.indexFromItem(self.item(self.count() - 1))
            rect = self.visualRect(last)
            return rect.bottom()
        return 0

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        super().dragEnterEvent(event)
        if event.isAccepted():
            self._drop_line.show()

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:
        super().dragMoveEvent(event)
        y = self._drop_line_y(event.position().toPoint())
        if y is not None:
            self._drop_line.setGeometry(0, y - 1, self.viewport().width(), 3)
            self._drop_line.show()
            self._drop_line.raise_()

    def dragLeaveEvent(self, event: QDragLeaveEvent) -> None:
        super().dragLeaveEvent(event)
        self._drop_line.hide()

    def dropEvent(self, event: QDropEvent) -> None:
        self._drop_line.hide()
        super().dropEvent(event)


class ExportWorker(QThread):
    """Background worker for set export. Uses its own DB connection (SQLite is not thread-safe)."""

    status = Signal(str)
    finished_ok = Signal()
    finished_error = Signal(str)

    def __init__(
        self,
        db_path: Path,
        setlist_id: int,
        setlist_name: str,
        band_layout_id: int | None,
        settings: SetExportSettings,
        player_ids_in_order: list[int] | None,
    ) -> None:
        super().__init__()
        self.db_path = db_path
        self.setlist_id = setlist_id
        self.setlist_name = setlist_name
        self.band_layout_id = band_layout_id
        self.settings = settings
        self.player_ids_in_order = player_ids_in_order

    def run(self) -> None:
        try:
            from ..db.schema import init_database
            conn = init_database(self.db_path)
            try:
                export_set(
                    conn,
                    self.setlist_id,
                    self.setlist_name,
                    self.band_layout_id,
                    self.settings,
                    self.player_ids_in_order,
                    status_callback=lambda msg: self.status.emit(msg),
                )
                self.finished_ok.emit()
            finally:
                conn.close()
        except Exception as e:
            self.finished_error.emit(str(e))


class SetExportDialog(QDialog):
    """Modal dialog for exporting a setlist to folder and/or zip."""

    def __init__(
        self,
        app_state,
        setlist_id: int,
        setlist_name: str,
        band_layout_id: int | None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.app_state = app_state
        self.setlist_id = setlist_id
        self.setlist_name = setlist_name
        self.band_layout_id = band_layout_id
        self._worker: ExportWorker | None = None

        self.setWindowTitle("Export Set")
        self.setMinimumSize(520, 480)
        self.resize(600, 540)

        prefs = get_set_export_prefs()
        default_dir = get_set_export_dir() or str(Path.home())
        output_dir = prefs.get("output_directory") or default_dir

        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()

        # Tab 1: Export Settings
        tab1 = QWidget()
        t1 = QVBoxLayout(tab1)
        dir_row = QHBoxLayout()
        dir_row.addWidget(QLabel("Output folder:"))
        self.dir_label = QLabel(output_dir or "(not set)")
        self.dir_label.setWordWrap(True)
        self.dir_label.setStyleSheet("color: #888;")
        dir_row.addWidget(self.dir_label, 1)
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._browse_output)
        dir_row.addWidget(browse_btn)
        t1.addLayout(dir_row)
        t1.addWidget(QLabel("Set name:"))
        self.set_name_edit = QLineEdit()
        self.set_name_edit.setText(_sanitize_set_name(setlist_name or "Untitled Set"))
        self.set_name_edit.setPlaceholderText("Name for folder/zip")
        t1.addWidget(self.set_name_edit)
        self.rename_check = QCheckBox("Rename ABC files using pattern")
        self.rename_check.setChecked(prefs.get("rename_abc_files", True))
        t1.addWidget(self.rename_check)
        self.folder_check = QCheckBox("Export as folder")
        self.folder_check.setChecked(prefs.get("export_as_folder", True))
        t1.addWidget(self.folder_check)
        self.zip_check = QCheckBox("Export as zip")
        self.zip_check.setChecked(prefs.get("export_as_zip", False))
        t1.addWidget(self.zip_check)
        self.csv_check = QCheckBox("Export CSV part sheet")
        self.csv_check.setChecked(prefs.get("export_csv_part_sheet", False))
        self.csv_check.toggled.connect(self._on_csv_toggled)
        t1.addWidget(self.csv_check)
        self.composer_check = QCheckBox("Include composer in CSV")
        self.composer_check.setChecked(prefs.get("include_composer_in_csv", True))
        t1.addWidget(self.composer_check)
        t1.addStretch()
        self.tabs.addTab(tab1, "Export Settings")

        # Tab 2: ABC File Renaming
        tab2 = QWidget()
        t2 = QVBoxLayout(tab2)
        t2.addWidget(QLabel("Replace spaces in variables with:"))
        self.whitespace_combo = QComboBox()
        self.whitespace_combo.addItems(SPACE_REPLACE_LABELS)
        idx = SPACE_REPLACE_CHARS.index(prefs.get("whitespace_replace", " "))
        if 0 <= idx < len(SPACE_REPLACE_CHARS):
            self.whitespace_combo.setCurrentIndex(idx)
        self.whitespace_combo.currentIndexChanged.connect(self._update_example)
        t2.addWidget(self.whitespace_combo)
        t2.addWidget(QLabel("Pattern for new ABC filenames:"))
        self.pattern_edit = QLineEdit()
        self.pattern_edit.setText(prefs.get("filename_pattern", "$SongIndex_$FileName"))
        self.pattern_edit.textChanged.connect(self._update_example)
        t2.addWidget(self.pattern_edit)
        self.example_label = QLabel()
        self.example_label.setStyleSheet("color: #888;")
        t2.addWidget(self.example_label)
        t2.addWidget(QLabel("Variables:"))
        var_text = (
            "$FileName — Original filename without .abc\n"
            "$SongIndex — 1-based position in setlist (e.g. 001)\n"
            "$PartCount — Number of parts\n"
            "$SongComposer — Composers (C: field)\n"
            "$SongTranscriber — Transcriber (Z: field)\n"
            "$SongLength — Duration in mm_ss format\n"
            "$SongTitle — Title (T: field)"
        )
        var_label = QLabel(var_text)
        var_label.setStyleSheet("color: #b4a8a8; font-size: 12px;")
        var_label.setWordWrap(True)
        t2.addWidget(var_label)
        t2.addStretch()
        self.tabs.addTab(tab2, "ABC File Renaming")

        # Tab 3: CSV Part Sheet
        tab3 = QWidget()
        t3 = QVBoxLayout(tab3)
        self.visible_col_radio = QRadioButton("Use visible table columns")
        self.visible_col_radio.setChecked(prefs.get("csv_use_visible_columns", True))
        self.visible_col_radio.toggled.connect(self._on_column_mode_changed)
        t3.addWidget(self.visible_col_radio)
        self.custom_col_radio = QRadioButton("Use custom columns")
        self.custom_col_radio.setChecked(not prefs.get("csv_use_visible_columns", True))
        self.custom_col_radio.toggled.connect(self._on_column_mode_changed)
        t3.addWidget(self.custom_col_radio)
        self.custom_cols_group = QGroupBox("Select columns")
        cc_layout = QVBoxLayout(self.custom_cols_group)
        self.csv_col_checks: dict[str, QCheckBox] = {}
        csv_enabled = prefs.get("csv_columns_enabled") or {}
        for col in CSV_AVAILABLE_COLUMNS:
            cb = QCheckBox(col)
            cb.setChecked(csv_enabled.get(col, col in CSV_DEFAULT_ENABLED))
            self.csv_col_checks[col] = cb
            cc_layout.addWidget(cb)
        t3.addWidget(self.custom_cols_group)
        t3.addWidget(QLabel("Part columns content (when no band layout):"))
        self.part_col_combo = QComboBox()
        self.part_col_combo.addItems(["Use Part Names", "Use Instrument Names"])
        self.part_col_combo.setCurrentIndex(0 if prefs.get("csv_part_columns", "part") == "part" else 1)
        t3.addWidget(self.part_col_combo)
        t3.addStretch()
        self.tabs.addTab(tab3, "CSV Part Sheet")

        # Tab 4: Player Column Order
        tab4 = QWidget()
        t4 = QVBoxLayout(tab4)
        t4.addWidget(QLabel("Drag to reorder player columns for CSV export:"))
        self.player_list = PlayerOrderListWidget()
        t4.addWidget(self.player_list)
        self.player_order_placeholder = QLabel("Assign a band layout to the setlist to configure player column order.")
        self.player_order_placeholder.setStyleSheet("color: #888;")
        self.player_order_placeholder.setWordWrap(True)
        t4.addWidget(self.player_order_placeholder)
        self.tabs.addTab(tab4, "Player Column Order")

        layout.addWidget(self.tabs)

        # Bottom: status, buttons
        self.status_label = QLabel()
        self.status_label.setStyleSheet("color: #888; min-height: 1.2em;")
        layout.addWidget(self.status_label)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(self.cancel_btn)
        self.export_btn = QPushButton("Export")
        self.export_btn.setDefault(True)
        self.export_btn.clicked.connect(self._start_export)
        btn_row.addWidget(self.export_btn)
        layout.addLayout(btn_row)

        self._output_dir = output_dir
        self._on_csv_toggled(self.csv_check.isChecked())
        self._on_column_mode_changed()
        self._load_player_order()
        self._update_player_tab_state()
        self._update_example()

    def _browse_output(self) -> None:
        start = self._output_dir or str(Path.home())
        path = QFileDialog.getExistingDirectory(self, "Select output folder", start)
        if path:
            self._output_dir = path
            self.dir_label.setText(path)
            self.dir_label.setStyleSheet("")

    def _on_csv_toggled(self, checked: bool) -> None:
        self.composer_check.setEnabled(checked)
        self.tabs.setTabEnabled(2, checked)

    def _on_column_mode_changed(self) -> None:
        use_visible = self.visible_col_radio.isChecked()
        self.custom_cols_group.setEnabled(not use_visible)
        self.composer_check.setEnabled(self.csv_check.isChecked() and use_visible)

    def _load_player_order(self) -> None:
        self.player_list.clear()
        if not self.band_layout_id:
            return
        slots = list_layout_slots_for_export(self.app_state.conn, self.band_layout_id)
        players = {p.id: p for p in list_players(self.app_state.conn) if p.id in {s.player_id for s in slots}}
        for s in slots:
            name = players[s.player_id].name if s.player_id in players else f"Player {s.player_id}"
            item = QListWidgetItem(name)
            item.setData(Qt.ItemDataRole.UserRole, s.player_id)
            self.player_list.addItem(item)

    def _update_player_tab_state(self) -> None:
        has_layout = self.band_layout_id is not None
        self.tabs.setTabEnabled(3, has_layout)
        self.tabs.setTabToolTip(3, "Assign a band layout to the setlist to configure player column order." if not has_layout else "")
        if has_layout:
            self.player_order_placeholder.hide()
            self.player_list.show()
        else:
            self.player_order_placeholder.show()
            self.player_list.hide()

    def _update_example(self) -> None:
        pattern = self.pattern_edit.text() or "$SongIndex_$FileName"
        idx = self.whitespace_combo.currentIndex()
        ws = SPACE_REPLACE_CHARS[idx] if 0 <= idx < len(SPACE_REPLACE_CHARS) else " "
        example = format_filename(
            pattern,
            file_path="my song.abc",
            index=2,
            title="My Song",
            composers="Composer Name",
            transcriber="Transcriber",
            duration_seconds=125,
            part_count=3,
            whitespace_replace=ws,
            part_count_zero_padded=True,
        )
        self.example_label.setText(f"Example: {example}")

    def _get_settings(self) -> SetExportSettings:
        csv_enabled = {col: self.csv_col_checks[col].isChecked() for col in CSV_AVAILABLE_COLUMNS}
        return SetExportSettings(
            output_directory=Path(self._output_dir or str(Path.home())),
            set_name=_sanitize_set_name(self.set_name_edit.text() or self.setlist_name or "Untitled Set"),
            export_as_folder=self.folder_check.isChecked(),
            export_as_zip=self.zip_check.isChecked(),
            rename_abc_files=self.rename_check.isChecked(),
            filename_pattern=self.pattern_edit.text() or "$SongIndex_$FileName",
            whitespace_replace=SPACE_REPLACE_CHARS[self.whitespace_combo.currentIndex()] if self.whitespace_combo.currentIndex() >= 0 else " ",
            part_count_zero_padded=True,
            export_csv_part_sheet=self.csv_check.isChecked(),
            include_composer_in_csv=self.composer_check.isChecked(),
            csv_use_visible_columns=self.visible_col_radio.isChecked(),
            csv_columns_enabled=csv_enabled,
            csv_part_columns="part" if self.part_col_combo.currentIndex() == 0 else "instrument",
        )

    def _get_player_ids_in_order(self) -> list[int] | None:
        if not self.band_layout_id or not self.player_list.isVisible():
            return None
        ids = []
        for i in range(self.player_list.count()):
            item = self.player_list.item(i)
            if item:
                pid = item.data(Qt.ItemDataRole.UserRole)
                if pid is not None:
                    ids.append(int(pid))
        # Always return list when we have band layout (even if empty) so order is saved and used
        return ids

    def _start_export(self) -> None:
        if not self.folder_check.isChecked() and not self.zip_check.isChecked():
            QMessageBox.warning(self, "Export", "Select at least one of: Export as folder, Export as zip.")
            return
        set_name = _sanitize_set_name(self.set_name_edit.text() or self.setlist_name or "Untitled Set")
        if not set_name:
            QMessageBox.warning(self, "Export", "Set name cannot be empty.")
            return
        if not self._output_dir:
            QMessageBox.warning(self, "Export", "Select an output folder.")
            return

        settings = self._get_settings()
        player_ids = self._get_player_ids_in_order()

        self.export_btn.setEnabled(False)
        self.cancel_btn.setEnabled(False)
        self.status_label.setText("Exporting...")
        self.status_label.setStyleSheet("")

        self._worker = ExportWorker(
            get_db_path(),
            self.setlist_id,
            self.setlist_name,
            self.band_layout_id,
            settings,
            player_ids,
        )
        self._worker.status.connect(self._on_status)
        self._worker.finished_ok.connect(self._on_export_ok)
        self._worker.finished_error.connect(self._on_export_error)
        self._worker.start()

    def _on_status(self, msg: str) -> None:
        self.status_label.setText(msg)

    def _on_export_ok(self) -> None:
        self.status_label.setText("Export finished.")
        self.status_label.setStyleSheet("color: #2ecc71;")
        self.export_btn.setEnabled(True)
        self.cancel_btn.setEnabled(True)
        self.cancel_btn.setText("Close")
        self.cancel_btn.clicked.disconnect()
        self.cancel_btn.clicked.connect(self.accept)
        # Save preferences
        prefs = {
            "output_directory": self._output_dir,
            "rename_abc_files": self.rename_check.isChecked(),
            "export_as_folder": self.folder_check.isChecked(),
            "export_as_zip": self.zip_check.isChecked(),
            "filename_pattern": self.pattern_edit.text(),
            "whitespace_replace": SPACE_REPLACE_CHARS[self.whitespace_combo.currentIndex()] if self.whitespace_combo.currentIndex() >= 0 else " ",
            "export_csv_part_sheet": self.csv_check.isChecked(),
            "include_composer_in_csv": self.composer_check.isChecked(),
            "csv_use_visible_columns": self.visible_col_radio.isChecked(),
            "csv_columns_enabled": {col: self.csv_col_checks[col].isChecked() for col in CSV_AVAILABLE_COLUMNS},
            "csv_part_columns": "part" if self.part_col_combo.currentIndex() == 0 else "instrument",
        }
        save_set_export_prefs(prefs)

    def _on_export_error(self, err: str) -> None:
        self.status_label.setText(err)
        self.status_label.setStyleSheet("color: #c0392b;")
        self.export_btn.setEnabled(True)
        self.cancel_btn.setEnabled(True)
        QMessageBox.critical(self, "Export Error", err)
