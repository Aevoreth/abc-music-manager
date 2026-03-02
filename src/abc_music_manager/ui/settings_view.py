"""
Settings: folder rules, statuses, account targets (PluginData).
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QPushButton,
    QLabel,
    QLineEdit,
    QComboBox,
    QCheckBox,
    QSpinBox,
    QDialog,
    QFormLayout,
    QMessageBox,
    QFileDialog,
    QHeaderView,
    QAbstractItemView,
    QStyle,
    QStyleOptionComboBox,
    QSizePolicy,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTimeEdit,
    QDateTimeEdit,
)
from PySide6.QtCore import Qt, QTime, QDateTime, QDate
from PySide6.QtGui import QColor, QPainter, QPen

from ..services.app_state import AppState
from ..services.preferences import (
    get_default_status_id,
    set_default_status_id,
    get_base_font_size,
    set_base_font_size,
    get_lotro_root,
    set_lotro_root,
    get_default_lotro_root,
    get_music_root,
    get_set_export_dir,
    get_set_export_dir_stored,
    set_set_export_dir,
    ensure_default_lotro_root,
    to_music_relative,
    resolve_music_path,
    get_default_filters,
    set_default_filters,
)
from ..db import list_folder_rules, add_folder_rule, update_folder_rule, delete_folder_rule, FolderRuleRow, RuleType
from ..db.status_repo import list_statuses, add_status, update_status, delete_status, reorder_statuses, StatusRow
from ..db.account_target import list_account_targets, add_account_target, update_account_target, delete_account_target, AccountTargetRow
from .theme import STATUS_CIRCLE_DIAMETER, COLOR_TEXT_SECONDARY
from .library_view import (
    LAST_PLAYED_TIME_OPTS,
    _index_for_seconds_ago,
    _rating_label,
    RatingComboBox,
    RatingComboDelegate,
    _time_edit_to_seconds,
    _seconds_to_time_edit,
)

# Data role for status color in status table Name column and default status combo
StatusColorRole = Qt.ItemDataRole.UserRole + 10


class StatusComboBox(QComboBox):
    """Combo box that shows the selected status with colored circle before the name (when closed and in dropdown)."""

    def paintEvent(self, event) -> None:
        opt = QStyleOptionComboBox()
        self.initStyleOption(opt)
        # Let the style draw frame and dropdown arrow only; we draw the content
        style = self.style()
        painter = QPainter(self)
        style.drawComplexControl(QStyle.ComplexControl.CC_ComboBox, opt, painter, self)
        # Content rect is where the current text goes (excludes dropdown arrow)
        edit_rect = style.subControlRect(
            QStyle.ComplexControl.CC_ComboBox, opt, QStyle.SubControl.SC_ComboBoxEditField, self
        )
        if edit_rect.isValid():
            # Fill content area so we overwrite any default text the style drew
            painter.fillRect(edit_rect, self.palette().color(self.palette().currentColorGroup(), self.palette().ColorRole.Base))
            idx = self.currentIndex()
            text = self.currentText() or ""
            color = None
            if idx >= 0:
                model_idx = self.model().index(idx, 0)
                if model_idx.isValid():
                    color = model_idx.data(StatusColorRole)
            try:
                qcolor = QColor(color) if color else self.palette().color(self.palette().currentColorGroup(), self.palette().ColorRole.Mid)
            except Exception:
                qcolor = self.palette().color(self.palette().currentColorGroup(), self.palette().ColorRole.Mid)
            painter.save()
            cy = edit_rect.center().y()
            r = STATUS_CIRCLE_DIAMETER // 2
            painter.setBrush(qcolor)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(edit_rect.x() + 2, cy - r, STATUS_CIRCLE_DIAMETER, STATUS_CIRCLE_DIAMETER)
            painter.setPen(QPen(self.palette().text().color()))
            text_rect = edit_rect.adjusted(STATUS_CIRCLE_DIAMETER + 6, 0, -4, 0)
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, text)
            painter.restore()
        painter.end()


class StatusComboDelegate(QStyledItemDelegate):
    """Paints combo items with colored circle before the status name."""

    def paint(self, painter: QPainter, option, index) -> None:
        text = index.data(Qt.ItemDataRole.DisplayRole) or ""
        color = index.data(StatusColorRole)
        opt = QStyleOptionViewItem(option)
        rect = opt.rect.adjusted(2, 0, -2, 0)
        cy = rect.center().y()
        r = STATUS_CIRCLE_DIAMETER // 2
        try:
            qcolor = QColor(color) if color else opt.palette.color(opt.palette.currentColorGroup(), opt.palette.ColorRole.Mid)
        except Exception:
            qcolor = opt.palette.color(opt.palette.currentColorGroup(), opt.palette.ColorRole.Mid)
        painter.save()
        painter.setBrush(qcolor)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(rect.x(), cy - r, STATUS_CIRCLE_DIAMETER, STATUS_CIRCLE_DIAMETER)
        painter.setPen(QPen(opt.palette.text().color()))
        text_rect = rect.adjusted(STATUS_CIRCLE_DIAMETER + 4, 0, 0, 0)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, text)
        painter.restore()


class StatusNameDelegate(QStyledItemDelegate):
    """Paints drag handle (column 0) and status name with colored circle (column 1) in status table."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

    def paint(self, painter: QPainter, option, index) -> None:
        col = index.column()
        opt = QStyleOptionViewItem(option)
        opt.showDecorationSelected = False
        rect = opt.rect.adjusted(2, 0, -2, 0)
        if col == 0:
            # Drag handle: two columns of three dots; use selected-cell background color
            painter.save()
            grip_color = opt.palette.color(opt.palette.currentColorGroup(), opt.palette.ColorRole.Highlight)
            painter.setBrush(grip_color)
            painter.setPen(Qt.PenStyle.NoPen)
            cx = rect.center().x()
            cy = rect.center().y()
            r = 2  # dot radius (4px diameter)
            for dx in (-4, 4):
                for dy in (-6, 0, 6):
                    painter.drawEllipse(int(cx + dx - r), int(cy + dy - r), 2 * r, 2 * r)
            painter.restore()
            return
        if col == 1:
            text = index.data(Qt.ItemDataRole.DisplayRole) or ""
            color = index.data(StatusColorRole)
            cy = rect.center().y()
            r = STATUS_CIRCLE_DIAMETER // 2
            try:
                qcolor = QColor(color) if color else opt.palette.text().color()
            except Exception:
                qcolor = opt.palette.text().color()
            painter.save()
            painter.setBrush(qcolor)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(rect.x(), cy - r, STATUS_CIRCLE_DIAMETER, STATUS_CIRCLE_DIAMETER)
            painter.setPen(QPen(opt.palette.text().color()))
            painter.drawText(rect.adjusted(STATUS_CIRCLE_DIAMETER + 4, 0, 0, 0), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, text)
            painter.restore()
            return
        super().paint(painter, option, index)


class StatusTableWidget(QTableWidget):
    """Table of statuses with drag handle; reorders and persists sort_order on drop."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._on_order_changed = None  # callable(list[int]) -> None

    def set_order_changed_callback(self, callback) -> None:
        self._on_order_changed = callback

    def dropEvent(self, event) -> None:
        super().dropEvent(event)
        if self._on_order_changed and event.isAccepted():
            ids = []
            for row in range(self.rowCount()):
                item = self.item(row, 1)
                if item:
                    sid = item.data(Qt.ItemDataRole.UserRole)
                    if sid is not None:
                        ids.append(int(sid))
            if ids:
                self._on_order_changed(ids)


class ExcludedDirEditor(QDialog):
    """Edit or add an excluded directory (relative to Music folder; not indexed; optionally in songbook export)."""

    def __init__(self, parent: QWidget | None, rule: FolderRuleRow | None = None) -> None:
        super().__init__(parent)
        self.rule = rule
        self.setWindowTitle("Edit excluded directory" if rule else "Add excluded directory")
        layout = QFormLayout(self)
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("Path relative to Music folder (e.g. OldSongs or Backup/2023)")
        self.include_in_export_check = QCheckBox("Include in songbook export")
        self.include_in_export_check.setToolTip("If checked, files under this path can be included when exporting SongbookData.plugindata")
        self.enabled_check = QCheckBox("Excluded from library scan")
        self.enabled_check.setChecked(True)
        layout.addRow("Path:", self.path_edit)
        layout.addRow("", self.include_in_export_check)
        layout.addRow("", self.enabled_check)
        if rule:
            self.path_edit.setText(resolve_music_path(rule.path) or rule.path)
            self.include_in_export_check.setChecked(rule.include_in_export)
            self.enabled_check.setChecked(rule.enabled)
        browse = QPushButton("Browse...")
        browse.clicked.connect(self._browse)
        layout.addRow("", browse)
        btns = QHBoxLayout()
        ok = QPushButton("OK")
        ok.clicked.connect(self.accept)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        btns.addWidget(ok)
        btns.addWidget(cancel)
        layout.addRow(btns)

    def _browse(self) -> None:
        start_dir = get_music_root() or ""
        path = QFileDialog.getExistingDirectory(
            self, "Select folder to exclude (under Music)", start_dir
        )
        if path:
            self.path_edit.setText(path)

    def get_values(self) -> tuple[str, bool, bool]:
        return (
            self.path_edit.text().strip(),
            self.include_in_export_check.isChecked(),
            self.enabled_check.isChecked(),
        )


class FolderRuleEditor(QDialog):
    """Legacy editor for any folder rule type (used only if needed elsewhere)."""

    def __init__(self, parent: QWidget | None, rule: FolderRuleRow | None = None) -> None:
        super().__init__(parent)
        self.rule = rule
        self.setWindowTitle("Edit folder rule" if rule else "Add folder rule")
        layout = QFormLayout(self)
        self.type_combo = QComboBox()
        self.type_combo.addItems(["library_root", "set_root", "exclude"])
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("Absolute path to folder")
        self.enabled_check = QCheckBox("Enabled")
        self.enabled_check.setChecked(True)
        layout.addRow("Type:", self.type_combo)
        layout.addRow("Path:", self.path_edit)
        layout.addRow("", self.enabled_check)
        if rule:
            self.type_combo.setCurrentText(rule.rule_type)
            self.path_edit.setText(rule.path)
            self.enabled_check.setChecked(rule.enabled)
        browse = QPushButton("Browse...")
        browse.clicked.connect(self._browse)
        layout.addRow("", browse)
        btns = QHBoxLayout()
        ok = QPushButton("OK")
        ok.clicked.connect(self.accept)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        btns.addWidget(ok)
        btns.addWidget(cancel)
        layout.addRow(btns)

    def _browse(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select folder")
        if path:
            self.path_edit.setText(path)

    def get_values(self) -> tuple[str, str, bool]:
        return (
            self.type_combo.currentText(),
            self.path_edit.text().strip(),
            self.enabled_check.isChecked(),
        )


def _parse_hex_color(s: str) -> QColor | None:
    s = (s or "").strip()
    if not s or s.startswith("#"):
        pass
    else:
        s = "#" + s
    if len(s) in (4, 7, 9) and all(c in "#0123456789AaBbCcDdEeFf" for c in s):
        q = QColor(s)
        if q.isValid():
            return q
    return None


class StatusEditor(QDialog):
    def __init__(self, parent: QWidget | None, status: StatusRow | None = None) -> None:
        super().__init__(parent)
        self.status = status
        self.setWindowTitle("Edit status" if status else "Add status")
        layout = QFormLayout(self)
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("e.g. New, Ready")
        color_row = QHBoxLayout()
        self.color_edit = QLineEdit()
        self.color_edit.setPlaceholderText("#RRGGBB or leave empty for theme default")
        self.color_edit.setMinimumWidth(120)
        self.color_picker_btn = QPushButton("Pick color...")
        self.color_picker_btn.clicked.connect(self._pick_color)
        color_row.addWidget(self.color_edit)
        color_row.addWidget(self.color_picker_btn)
        layout.addRow("Name:", self.name_edit)
        layout.addRow("Color (hex):", color_row)
        if status:
            self.name_edit.setText(status.name)
            self.color_edit.setText(status.color or "")
        ok = QPushButton("OK")
        ok.clicked.connect(self.accept)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        layout.addRow(ok, cancel)

    def _pick_color(self) -> None:
        from PySide6.QtWidgets import QColorDialog
        initial = _parse_hex_color(self.color_edit.text())
        if not initial or not initial.isValid():
            initial = QColor(200, 200, 200)
        color = QColorDialog.getColor(initial, self, "Choose status color")
        if color.isValid():
            self.color_edit.setText(color.name())

    def get_values(self) -> tuple[str, str | None]:
        color = self.color_edit.text().strip() or None
        return (self.name_edit.text().strip(), color)


class AccountTargetEditor(QDialog):
    def __init__(self, parent: QWidget | None, target: AccountTargetRow | None = None) -> None:
        super().__init__(parent)
        self.target = target
        self.setWindowTitle("Edit account target" if target else "Add account target")
        layout = QFormLayout(self)
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Account name")
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("Path to PluginData folder")
        self.enabled_check = QCheckBox("Enabled")
        self.enabled_check.setChecked(True)
        layout.addRow("Account name:", self.name_edit)
        layout.addRow("PluginData path:", self.path_edit)
        layout.addRow("", self.enabled_check)
        if target:
            self.name_edit.setText(target.account_name)
            self.path_edit.setText(target.plugin_data_path)
            self.enabled_check.setChecked(target.enabled)
        browse = QPushButton("Browse...")
        browse.clicked.connect(self._browse)
        layout.addRow("", browse)
        ok = QPushButton("OK")
        ok.clicked.connect(self.accept)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        layout.addRow(ok, cancel)

    def _browse(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select PluginData folder")
        if path:
            self.path_edit.setText(path)

    def get_values(self) -> tuple[str, str, bool]:
        return (
            self.name_edit.text().strip(),
            self.path_edit.text().strip(),
            self.enabled_check.isChecked(),
        )


class SettingsView(QWidget):
    def __init__(self, app_state: AppState, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.app_state = app_state
        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_appearance_tab(), "Appearance")
        self.tabs.addTab(self._build_default_filters_tab(), "Default filters")
        self.tabs.addTab(self._build_folder_rules_tab(), "Folder rules")
        self.tabs.addTab(self._build_statuses_tab(), "Statuses")
        self.tabs.addTab(self._build_account_targets_tab(), "Account targets")
        self.tabs.currentChanged.connect(self._on_settings_tab_changed)
        layout.addWidget(self.tabs)

    def _build_appearance_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        font_row = QHBoxLayout()
        self.base_font_default_check = QCheckBox("Use system default font size")
        self.base_font_default_check.stateChanged.connect(self._on_base_font_default_changed)
        font_row.addWidget(self.base_font_default_check)
        font_row.addStretch()
        v.addLayout(font_row)
        pt_row = QHBoxLayout()
        pt_row.addWidget(QLabel("Base font size (pt):"))
        self.base_font_size_spin = QSpinBox()
        self.base_font_size_spin.setRange(8, 16)
        self.base_font_size_spin.setSuffix(" pt")
        self.base_font_size_spin.setMinimumWidth(100)
        pt_row.addWidget(self.base_font_size_spin)
        pt_row.addWidget(QLabel("(8–16 pt; applies immediately)"))
        pt_row.addStretch()
        v.addLayout(pt_row)
        from PySide6.QtCore import QSignalBlocker
        saved = get_base_font_size()
        with QSignalBlocker(self.base_font_size_spin), QSignalBlocker(self.base_font_default_check):
            if saved == 0:
                self.base_font_default_check.setChecked(True)
                self.base_font_size_spin.setEnabled(False)
                self.base_font_size_spin.setValue(10)
            else:
                self.base_font_default_check.setChecked(False)
                self.base_font_size_spin.setValue(max(8, min(16, saved)))
        self.base_font_size_spin.valueChanged.connect(self._on_base_font_size_changed)
        v.addStretch()
        return w

    def _build_default_filters_tab(self) -> QWidget:
        """Settings tab for default library filter values (used on startup and when Reset Filters is clicked)."""
        w = QWidget()
        v = QVBoxLayout(w)
        desc = QLabel(
            "Configure default values for library filters. These apply when you open the app and when you click Reset Filters."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY};")
        v.addWidget(desc)

        defaults = get_default_filters()

        # Main row: In set, Rating
        main_row = QHBoxLayout()
        main_row.addWidget(QLabel("In set:"))
        self._df_in_set_combo = QComboBox()
        self._df_in_set_combo.addItem("Either", None)
        self._df_in_set_combo.addItem("Yes", "yes")
        self._df_in_set_combo.addItem("No", "no")
        in_set = defaults.get("in_set")
        for i in range(self._df_in_set_combo.count()):
            if self._df_in_set_combo.itemData(i) == in_set:
                self._df_in_set_combo.setCurrentIndex(i)
                break
        main_row.addWidget(self._df_in_set_combo)

        main_row.addWidget(QLabel("Rating:"))
        self._df_rating_from_combo = RatingComboBox()
        self._df_rating_from_combo.setItemDelegate(RatingComboDelegate(self._df_rating_from_combo))
        for i in range(6):
            self._df_rating_from_combo.addItem(_rating_label(i), i)
        self._df_rating_from_combo.setCurrentIndex(int(defaults.get("rating_from", 0)))
        main_row.addWidget(self._df_rating_from_combo)
        main_row.addWidget(QLabel("to"))
        self._df_rating_to_combo = RatingComboBox()
        self._df_rating_to_combo.setItemDelegate(RatingComboDelegate(self._df_rating_to_combo))
        for i in range(6):
            self._df_rating_to_combo.addItem(_rating_label(i), i)
        r_to = int(defaults.get("rating_to", 5))
        self._df_rating_to_combo.setCurrentIndex(min(5, max(0, r_to)))
        main_row.addWidget(self._df_rating_to_combo)
        main_row.addStretch()
        v.addLayout(main_row)

        # Duration
        dur_row = QHBoxLayout()
        dur_row.addWidget(QLabel("Duration:"))
        self._df_duration_min_none = QCheckBox("None")
        self._df_duration_min_none.setChecked(defaults.get("duration_min_none", True))
        self._df_duration_min_none.toggled.connect(lambda: self._df_duration_min_edit.setEnabled(not self._df_duration_min_none.isChecked()))
        dur_row.addWidget(self._df_duration_min_none)
        self._df_duration_min_edit = QTimeEdit()
        self._df_duration_min_edit.setDisplayFormat("m:ss")
        self._df_duration_min_edit.setTime(QTime(0, 0, 0).addSecs(int(defaults.get("duration_min_sec", 0))))
        self._df_duration_min_edit.setEnabled(not self._df_duration_min_none.isChecked())
        self._df_duration_min_edit.setMinimumWidth(88)
        dur_row.addWidget(self._df_duration_min_edit)
        dur_row.addWidget(QLabel("to"))
        self._df_duration_max_none = QCheckBox("None")
        self._df_duration_max_none.setChecked(defaults.get("duration_max_none", True))
        self._df_duration_max_none.toggled.connect(lambda: self._df_duration_max_edit.setEnabled(not self._df_duration_max_none.isChecked()))
        dur_row.addWidget(self._df_duration_max_none)
        self._df_duration_max_edit = QTimeEdit()
        self._df_duration_max_edit.setDisplayFormat("m:ss")
        self._df_duration_max_edit.setTime(QTime(0, 0, 0).addSecs(int(defaults.get("duration_max_sec", 1200))))
        self._df_duration_max_edit.setEnabled(not self._df_duration_max_none.isChecked())
        self._df_duration_max_edit.setMinimumWidth(88)
        dur_row.addWidget(self._df_duration_max_edit)
        dur_row.addStretch()
        v.addLayout(dur_row)

        # Last played
        lp_row = QHBoxLayout()
        lp_row.addWidget(QLabel("Last played:"))
        self._df_last_played_mode_combo = QComboBox()
        self._df_last_played_mode_combo.addItem("Time range", "time")
        self._df_last_played_mode_combo.addItem("Date range", "date")
        mode = defaults.get("last_played_mode", "time")
        self._df_last_played_mode_combo.setCurrentIndex(0 if mode == "time" else 1)
        self._df_last_played_mode_combo.currentIndexChanged.connect(self._on_df_last_played_mode_changed)
        lp_row.addWidget(self._df_last_played_mode_combo)
        self._df_last_played_from_combo = QComboBox()
        for label, sec in LAST_PLAYED_TIME_OPTS:
            self._df_last_played_from_combo.addItem(label, sec)
        sec_from = defaults.get("last_played_from_seconds_ago", 0)
        self._df_last_played_from_combo.setCurrentIndex(_index_for_seconds_ago(sec_from))
        lp_row.addWidget(self._df_last_played_from_combo)
        self._df_last_played_to_combo = QComboBox()
        for label, sec in LAST_PLAYED_TIME_OPTS:
            self._df_last_played_to_combo.addItem(label, sec)
        sec_to = defaults.get("last_played_to_seconds_ago")
        self._df_last_played_to_combo.setCurrentIndex(
            _index_for_seconds_ago(sec_to) if sec_to is not None else self._df_last_played_to_combo.count() - 1
        )
        lp_row.addWidget(self._df_last_played_to_combo)
        self._df_last_played_from_combo.setVisible(mode == "time")
        self._df_last_played_to_combo.setVisible(mode == "time")
        self._df_last_played_from_dt = QDateTimeEdit()
        self._df_last_played_from_dt.setCalendarPopup(True)
        self._df_last_played_from_dt.setDisplayFormat("yyyy-MM-dd hh:mm")
        self._df_last_played_from_dt.setVisible(mode == "date")
        lp_row.addWidget(self._df_last_played_from_dt)
        self._df_last_played_to_dt = QDateTimeEdit()
        self._df_last_played_to_dt.setCalendarPopup(True)
        self._df_last_played_to_dt.setDisplayFormat("yyyy-MM-dd hh:mm")
        self._df_last_played_to_dt.setVisible(mode == "date")
        lp_row.addWidget(self._df_last_played_to_dt)
        lp_row.addStretch()
        v.addLayout(lp_row)

        # Parts
        parts_row = QHBoxLayout()
        parts_row.addWidget(QLabel("Parts:"))
        self._df_parts_min_combo = QComboBox()
        for n in range(1, 25):
            self._df_parts_min_combo.addItem(str(n), n)
        self._df_parts_min_combo.setCurrentIndex(int(defaults.get("parts_min", 1)) - 1)
        parts_row.addWidget(self._df_parts_min_combo)
        parts_row.addWidget(QLabel("to"))
        self._df_parts_max_combo = QComboBox()
        for n in range(1, 25):
            self._df_parts_max_combo.addItem(str(n), n)
        self._df_parts_max_combo.setCurrentIndex(int(defaults.get("parts_max", 24)) - 1)
        parts_row.addWidget(self._df_parts_max_combo)
        parts_row.addStretch()
        v.addLayout(parts_row)

        # Status filter defaults
        status_row = QHBoxLayout()
        status_row.addWidget(QLabel("Default status filter:"))
        status_desc = QLabel("(All = no status filter by default)")
        status_desc.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY};")
        status_row.addWidget(status_desc)
        status_row.addStretch()
        v.addLayout(status_row)
        self._df_status_checkboxes: list[tuple[QCheckBox, int]] = []
        status_cb_layout = QHBoxLayout()
        self._df_status_all_cb = QCheckBox("All statuses")
        self._df_status_all_cb.setObjectName("df_status_all")
        self._df_status_all_cb.toggled.connect(self._on_df_status_all_toggled)
        status_cb_layout.addWidget(self._df_status_all_cb)
        default_status_ids = defaults.get("status_ids") or []
        for s in list_statuses(self.app_state.conn):
            cb = QCheckBox(s.name)
            cb.setChecked(s.id in default_status_ids)
            cb.setProperty("status_id", s.id)
            cb.toggled.connect(self._on_df_status_cb_toggled)
            self._df_status_checkboxes.append((cb, s.id))
            status_cb_layout.addWidget(cb)
        if not default_status_ids:
            self._df_status_all_cb.setChecked(True)
        status_cb_layout.addStretch()
        v.addLayout(status_cb_layout)

        save_btn = QPushButton("Save as default filters")
        save_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        save_btn.clicked.connect(self._on_save_default_filters)
        v.addWidget(save_btn)
        v.addStretch()
        return w

    def _on_df_last_played_mode_changed(self) -> None:
        is_time = self._df_last_played_mode_combo.currentData() == "time"
        self._df_last_played_from_combo.setVisible(is_time)
        self._df_last_played_to_combo.setVisible(is_time)
        self._df_last_played_from_dt.setVisible(not is_time)
        self._df_last_played_to_dt.setVisible(not is_time)

    def _on_df_status_all_toggled(self, checked: bool) -> None:
        if checked:
            for cb, _ in self._df_status_checkboxes:
                cb.blockSignals(True)
                cb.setChecked(False)
                cb.blockSignals(False)

    def _on_df_status_cb_toggled(self) -> None:
        if any(cb.isChecked() for cb, _ in self._df_status_checkboxes):
            self._df_status_all_cb.blockSignals(True)
            self._df_status_all_cb.setChecked(False)
            self._df_status_all_cb.blockSignals(False)

    def _on_save_default_filters(self) -> None:
        in_set = self._df_in_set_combo.currentData()
        r_from = self._df_rating_from_combo.currentData()
        r_to = self._df_rating_to_combo.currentData()
        filters = {
            "in_set": in_set,
            "rating_from": int(r_from) if r_from is not None else 0,
            "rating_to": int(r_to) if r_to is not None else 5,
            "duration_min_none": self._df_duration_min_none.isChecked(),
            "duration_max_none": self._df_duration_max_none.isChecked(),
            "duration_min_sec": _time_edit_to_seconds(self._df_duration_min_edit) if not self._df_duration_min_none.isChecked() else 0,
            "duration_max_sec": _time_edit_to_seconds(self._df_duration_max_edit) if not self._df_duration_max_none.isChecked() else 1200,
            "last_played_mode": self._df_last_played_mode_combo.currentData() or "time",
            "last_played_from_seconds_ago": self._df_last_played_from_combo.currentData() if self._df_last_played_mode_combo.currentData() == "time" else 0,
            "last_played_to_seconds_ago": self._df_last_played_to_combo.currentData() if self._df_last_played_mode_combo.currentData() == "time" else None,
            "last_played_from_iso": self._df_last_played_from_dt.dateTime().toPython().isoformat() if self._df_last_played_mode_combo.currentData() == "date" else None,
            "last_played_to_iso": self._df_last_played_to_dt.dateTime().toPython().isoformat() if self._df_last_played_mode_combo.currentData() == "date" else None,
            "parts_min": self._df_parts_min_combo.currentData() or 1,
            "parts_max": self._df_parts_max_combo.currentData() or 24,
            "status_ids": [sid for cb, sid in self._df_status_checkboxes if cb.isChecked()],
        }
        set_default_filters(filters)
        QMessageBox.information(self, "Saved", "Default filters have been saved.")

    def _on_base_font_default_changed(self, _state: int = 0) -> None:
        use_default = self.base_font_default_check.isChecked()
        self.base_font_size_spin.setEnabled(not use_default)
        if use_default:
            set_base_font_size(0)
            app = QApplication.instance()
            if app:
                from PySide6.QtGui import QFontDatabase
                system_font = QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont)
                app.setFont(system_font)
                self._apply_font_to_widgets(app, app.font())
        else:
            self._on_base_font_size_changed(self.base_font_size_spin.value())

    def _on_base_font_size_changed(self, value: int) -> None:
        set_base_font_size(value)
        app = QApplication.instance()
        if app and value >= 8:
            from PySide6.QtGui import QFont
            font = QFont(app.font())
            font.setPointSize(value)
            app.setFont(font)
            self._apply_font_to_widgets(app, app.font())
        elif app:
            from PySide6.QtGui import QFontDatabase
            app.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont))
            self._apply_font_to_widgets(app, app.font())

    def _apply_font_to_widgets(self, app: QApplication, font) -> None:
        """Propagate application font to all existing top-level widgets so changes apply without restart."""
        from PySide6.QtWidgets import QWidget

        def set_font_recursive(w: QWidget) -> None:
            w.setFont(font)
            for child in w.findChildren(QWidget):
                child.setFont(font)

        for w in app.topLevelWidgets():
            if w.isWidgetType():
                set_font_recursive(w)

    def _build_folder_rules_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)

        # Lord of the Rings Online root directory (contains \Music\ and \PluginData\<account>\AllServers\)
        lotro_group = QWidget()
        lotro_layout = QVBoxLayout(lotro_group)
        lotro_layout.addWidget(QLabel("Lord of the Rings Online directory"))
        lotro_desc = QLabel(
            "This is the main LOTRO directory, usually in your Documents library (e.g. Documents\\The Lord of the Rings Online). "
            "It contains the Music folder (library) and the PluginData folder for SongbookData.plugindata."
        )
        lotro_desc.setWordWrap(True)
        lotro_desc.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY};")
        lotro_layout.addWidget(lotro_desc)
        self.lotro_path_edit = QLineEdit()
        self.lotro_path_edit.setReadOnly(True)
        self.lotro_path_edit.setPlaceholderText("Not set — use default if it exists (e.g. Documents\\The Lord of the Rings Online)")
        lotro_layout.addWidget(self.lotro_path_edit)
        set_lotro_btn = QPushButton("Set Directory")
        set_lotro_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        set_lotro_btn.clicked.connect(self._on_change_lotro_root)
        lotro_layout.addWidget(set_lotro_btn)
        v.addWidget(lotro_group)

        # Set Export directory (one only; not scanned; included in SongbookData export when implemented)
        set_export_group = QWidget()
        set_export_layout = QVBoxLayout(set_export_group)
        set_export_layout.addWidget(QLabel("Set Export directory"))
        set_export_desc = QLabel("Single directory for set export. Not scanned for the library; included when exporting SongbookData.plugindata.")
        set_export_desc.setWordWrap(True)
        set_export_desc.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY};")
        set_export_layout.addWidget(set_export_desc)
        self.set_export_path_edit = QLineEdit()
        self.set_export_path_edit.setReadOnly(True)
        self.set_export_path_edit.setPlaceholderText("Not set")
        set_export_layout.addWidget(self.set_export_path_edit)
        set_export_btn_row = QHBoxLayout()
        set_export_btn = QPushButton("Set Directory")
        set_export_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        set_export_btn.clicked.connect(self._on_set_export_dir)
        set_export_btn_row.addWidget(set_export_btn)
        clear_export_btn = QPushButton("Clear")
        clear_export_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        clear_export_btn.clicked.connect(self._on_clear_set_export_dir)
        set_export_btn_row.addWidget(clear_export_btn)
        set_export_btn_row.addStretch()
        set_export_layout.addLayout(set_export_btn_row)
        v.addWidget(set_export_group)

        # Excluded directories table
        excl_label = QLabel("Excluded directories")
        v.addWidget(excl_label)
        excl_desc = QLabel("Paths listed here are not indexed in the library. You can choose whether to include them in songbook export.")
        excl_desc.setWordWrap(True)
        excl_desc.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY};")
        v.addWidget(excl_desc)
        add_excl_btn = QPushButton("Add Excluded Directory")
        add_excl_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        add_excl_btn.clicked.connect(self._add_excluded_dir)
        v.addWidget(add_excl_btn)
        self.folder_table = QTableWidget()
        self.folder_table.setColumnCount(3)
        self.folder_table.setHorizontalHeaderLabels(["Path", "Songbook", "Actions"])
        self.folder_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.folder_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        v.addWidget(self.folder_table)

        self._refresh_lotro_and_set_export_display()
        self._refresh_folder_rules()
        return w

    def _on_settings_tab_changed(self, index: int) -> None:
        # Folder rules tab is index 1: ensure default LOTRO path is detected/saved and refresh display
        if index == 1:
            ensure_default_lotro_root()
            self._refresh_lotro_and_set_export_display()

    def _refresh_lotro_and_set_export_display(self) -> None:
        lotro = get_lotro_root()
        if not lotro and get_default_lotro_root():
            lotro = get_default_lotro_root()
        self.lotro_path_edit.setText(lotro or "")
        self.set_export_path_edit.setText(get_set_export_dir_stored() or "")

    def _on_change_lotro_root(self) -> None:
        current = get_lotro_root() or get_default_lotro_root()
        path = QFileDialog.getExistingDirectory(
            self,
            "Select Lord of the Rings Online directory",
            current or "",
        )
        if path:
            set_lotro_root(path)
            self._refresh_lotro_and_set_export_display()

    def _on_set_export_dir(self) -> None:
        current = get_set_export_dir()
        start_dir = get_music_root() or current or ""
        path = QFileDialog.getExistingDirectory(
            self,
            "Select Set Export directory (relative to Music folder)",
            start_dir,
        )
        if path:
            set_set_export_dir(path)
            self._refresh_lotro_and_set_export_display()

    def _on_clear_set_export_dir(self) -> None:
        set_set_export_dir("")
        self._refresh_lotro_and_set_export_display()

    def _refresh_folder_rules(self) -> None:
        rules = [r for r in list_folder_rules(self.app_state.conn) if r.rule_type == "exclude"]
        self.folder_table.setRowCount(len(rules))
        for i, r in enumerate(rules):
            self.folder_table.setItem(i, 0, QTableWidgetItem(r.path))
            self.folder_table.setItem(i, 1, QTableWidgetItem("Yes" if r.include_in_export else "No"))
            edit_btn = QPushButton("Edit")
            edit_btn.setMinimumWidth(52)
            edit_btn.clicked.connect(lambda checked=False, row=r: self._edit_excluded_dir(row))
            del_btn = QPushButton("Delete")
            del_btn.setMinimumWidth(58)
            del_btn.clicked.connect(lambda checked=False, row=r: self._delete_folder_rule(row))
            cell = QWidget()
            cell_layout = QHBoxLayout(cell)
            cell_layout.setContentsMargins(4, 2, 4, 2)
            cell_layout.addWidget(edit_btn)
            cell_layout.addWidget(del_btn)
            self.folder_table.setCellWidget(i, 2, cell)

    def _add_excluded_dir(self) -> None:
        dlg = ExcludedDirEditor(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            path, include_in_export, enabled = dlg.get_values()
            if not path:
                QMessageBox.warning(self, "Error", "Path is required.")
                return
            path_to_save = to_music_relative(path)
            add_folder_rule(
                self.app_state.conn,
                "exclude",
                path_to_save,
                enabled=enabled,
                include_in_export=include_in_export,
            )
            self._refresh_folder_rules()

    def _edit_excluded_dir(self, rule: FolderRuleRow) -> None:
        dlg = ExcludedDirEditor(self, rule)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            path, include_in_export, enabled = dlg.get_values()
            if not path:
                QMessageBox.warning(self, "Error", "Path is required.")
                return
            path_to_save = to_music_relative(path)
            update_folder_rule(
                self.app_state.conn,
                rule.id,
                path=path_to_save,
                enabled=enabled,
                include_in_export=include_in_export,
            )
            self._refresh_folder_rules()

    def _delete_folder_rule(self, rule: FolderRuleRow) -> None:
        if QMessageBox.question(
            self, "Confirm", f"Remove excluded directory:\n{rule.path}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) == QMessageBox.StandardButton.Yes:
            delete_folder_rule(self.app_state.conn, rule.id)
            self._refresh_folder_rules()

    def _build_statuses_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        default_row = QHBoxLayout()
        default_row.addWidget(QLabel("Default status:"))
        self.default_status_combo = StatusComboBox()
        self.default_status_combo.setItemDelegate(StatusComboDelegate(self.default_status_combo))
        self.default_status_combo.setMinimumWidth(180)
        default_row.addWidget(self.default_status_combo)
        default_row.addStretch()
        v.addLayout(default_row)
        add_row = QHBoxLayout()
        add_row.addWidget(QLabel("Add new status:"))
        add_btn = QPushButton("Add status")
        add_btn.clicked.connect(self._add_status)
        add_row.addWidget(add_btn)
        add_row.addStretch()
        v.addLayout(add_row)
        self.status_table = StatusTableWidget()
        self.status_table.setObjectName("status_table")
        self.status_table.setColumnCount(3)
        self.status_table.setHorizontalHeaderLabels(["", "Name", "Actions"])
        self.status_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.status_table.setColumnWidth(0, 24)
        self.status_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        self.status_table.setColumnWidth(1, 180)
        self.status_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.status_table.setItemDelegate(StatusNameDelegate(self.status_table))
        # SingleSelection required for InternalMove drag to work; style selection invisible so rows look unselected
        self.status_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.status_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.status_table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.status_table.verticalHeader().setDefaultSectionSize(40)
        self.status_table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self.status_table.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.status_table.setDragDropOverwriteMode(False)
        self.status_table.setDragEnabled(True)
        self.status_table.setAcceptDrops(True)
        self.status_table.setDropIndicatorShown(True)
        self.status_table.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.status_table.setStyleSheet(
            "QTableWidget#status_table::item:selected { background: palette(base); color: palette(text); }"
        )
        self.status_table.set_order_changed_callback(self._on_status_order_changed)
        v.addWidget(self.status_table)
        self._refresh_statuses()
        self._load_default_status_combo()
        self.default_status_combo.currentIndexChanged.connect(self._on_default_status_changed)
        return w

    def _on_status_order_changed(self, id_order: list[int]) -> None:
        reorder_statuses(self.app_state.conn, id_order)
        self._refresh_statuses()

    def _load_default_status_combo(self) -> None:
        from PySide6.QtCore import QSignalBlocker
        with QSignalBlocker(self.default_status_combo):
            self.default_status_combo.clear()
            for r in list_statuses(self.app_state.conn):
                i = self.default_status_combo.count()
                self.default_status_combo.addItem(r.name, r.id)
                self.default_status_combo.setItemData(i, r.color, StatusColorRole)
            current = get_default_status_id()
            idx = self.default_status_combo.findData(current)
            if idx >= 0:
                self.default_status_combo.setCurrentIndex(idx)
            else:
                # Default "Default status" is New (first in list)
                self.default_status_combo.setCurrentIndex(0)
                if self.default_status_combo.count() > 0:
                    set_default_status_id(self.default_status_combo.currentData())

    def _on_default_status_changed(self) -> None:
        data = self.default_status_combo.currentData()
        if data is not None:
            set_default_status_id(data)

    def _refresh_statuses(self) -> None:
        rows = list_statuses(self.app_state.conn)
        self.status_table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            # Column 0: drag handle (delegate paints it); placeholder item, selectable so row can be dragged
            self.status_table.setItem(i, 0, QTableWidgetItem(""))
            self.status_table.item(i, 0).setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            # Column 1: name (delegate paints circle + name); store id and color; selectable so row can be dragged
            name_item = QTableWidgetItem(r.name)
            name_item.setData(Qt.ItemDataRole.UserRole, r.id)
            name_item.setData(StatusColorRole, r.color)
            name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.status_table.setItem(i, 1, name_item)
            # Column 2: actions
            edit_btn = QPushButton("Edit")
            edit_btn.clicked.connect(lambda checked=False, row=r: self._edit_status(row))
            del_btn = QPushButton("Delete")
            del_btn.clicked.connect(lambda checked=False, row=r: self._delete_status(row))
            cell = QWidget()
            cell_layout = QHBoxLayout(cell)
            cell_layout.setContentsMargins(4, 2, 4, 2)
            cell_layout.addWidget(edit_btn)
            cell_layout.addWidget(del_btn)
            self.status_table.setCellWidget(i, 2, cell)
        self.status_table.setRowCount(len(rows))
        self._load_default_status_combo()

    def _add_status(self) -> None:
        dlg = StatusEditor(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            name, color = dlg.get_values()
            if not name:
                QMessageBox.warning(self, "Error", "Name is required.")
                return
            add_status(self.app_state.conn, name, color=color, sort_order=len(list_statuses(self.app_state.conn)))
            self._refresh_statuses()

    def _edit_status(self, status: StatusRow) -> None:
        dlg = StatusEditor(self, status)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            name, color = dlg.get_values()
            if not name:
                QMessageBox.warning(self, "Error", "Name is required.")
                return
            update_status(self.app_state.conn, status.id, name=name, color=color)
            self._refresh_statuses()

    def _delete_status(self, status: StatusRow) -> None:
        if QMessageBox.question(
            self, "Confirm", f"Delete status '{status.name}'? Songs using it will have no status.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) == QMessageBox.StandardButton.Yes:
            delete_status(self.app_state.conn, status.id)
            self._refresh_statuses()

    def _build_account_targets_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        btn_row = QHBoxLayout()
        scan_btn = QPushButton("Scan Account Targets")
        scan_btn.clicked.connect(self._scan_account_targets)
        add_btn = QPushButton("Add account target")
        add_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        btn_row.addWidget(scan_btn)
        btn_row.addStretch()
        btn_row.addWidget(add_btn)
        v.addLayout(btn_row)
        self.account_table = QTableWidget()
        self.account_table.setColumnCount(4)
        self.account_table.setHorizontalHeaderLabels(["Account", "Path", "Enabled", "Actions"])
        for col in range(4):
            self.account_table.horizontalHeader().setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        v.addWidget(self.account_table)
        add_btn.clicked.connect(self._add_account_target)
        self._refresh_account_targets()
        return w

    def _scan_account_targets(self) -> None:
        lotro_root = get_lotro_root()
        if not lotro_root:
            QMessageBox.warning(
                self,
                "Scan Account Targets",
                "LOTRO root directory is not set. Configure it in the Folder rules tab.",
            )
            return
        plugin_data_dir = Path(lotro_root) / "PluginData"
        if not plugin_data_dir.exists() or not plugin_data_dir.is_dir():
            QMessageBox.warning(
                self,
                "Scan Account Targets",
                "PluginData folder not found."
            )
            return
        existing = set()
        for r in list_account_targets(self.app_state.conn):
            existing.add(r.account_name.lower())
            existing.add((r.plugin_data_path or "").lower())
        added = 0
        for child in plugin_data_dir.iterdir():
            if child.is_dir():
                account_name = child.name
                plugin_data_path = str(plugin_data_dir / account_name / "AllServers")
                if account_name.lower() not in existing and plugin_data_path.lower() not in existing:
                    add_account_target(self.app_state.conn, account_name, plugin_data_path, enabled=True)
                    added += 1
                    existing.add(account_name.lower())
                    existing.add(plugin_data_path.lower())
        self._refresh_account_targets()
        if added > 0:
            QMessageBox.information(
                self,
                "Scan Account Targets",
                f"Found {added} new account(s)."
            )

    def _refresh_account_targets(self) -> None:
        rows = list_account_targets(self.app_state.conn)
        self.account_table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            self.account_table.setItem(i, 0, QTableWidgetItem(r.account_name))
            self.account_table.setItem(i, 1, QTableWidgetItem(r.plugin_data_path))
            enabled_check = QCheckBox()
            enabled_check.setChecked(r.enabled)
            enabled_check.stateChanged.connect(
                lambda state, target=r: self._on_account_target_enabled_changed(target, state)
            )
            cell_widget = QWidget()
            cell_layout = QHBoxLayout(cell_widget)
            cell_layout.setContentsMargins(4, 4, 4, 4)
            cell_layout.addWidget(enabled_check)
            cell_layout.addStretch()
            self.account_table.setCellWidget(i, 2, cell_widget)
            edit_btn = QPushButton("Edit")
            edit_btn.clicked.connect(lambda checked=False, row=r: self._edit_account_target(row))
            del_btn = QPushButton("Delete")
            del_btn.clicked.connect(lambda checked=False, row=r: self._delete_account_target(row))
            cell = QWidget()
            cell_layout = QHBoxLayout(cell)
            cell_layout.addWidget(edit_btn)
            cell_layout.addWidget(del_btn)
            self.account_table.setCellWidget(i, 3, cell)
        self.account_table.setRowCount(len(rows))

    def _on_account_target_enabled_changed(self, target: AccountTargetRow, state: int) -> None:
        enabled = state == int(Qt.CheckState.Checked)
        update_account_target(self.app_state.conn, target.id, enabled=enabled)

    def _add_account_target(self) -> None:
        dlg = AccountTargetEditor(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            name, path, enabled = dlg.get_values()
            if not name or not path:
                QMessageBox.warning(self, "Error", "Account name and path are required.")
                return
            add_account_target(self.app_state.conn, name, path, enabled)
            self._refresh_account_targets()

    def _edit_account_target(self, target: AccountTargetRow) -> None:
        dlg = AccountTargetEditor(self, target)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            name, path, enabled = dlg.get_values()
            if not name or not path:
                QMessageBox.warning(self, "Error", "Account name and path are required.")
                return
            update_account_target(self.app_state.conn, target.id, account_name=name, plugin_data_path=path, enabled=enabled)
            self._refresh_account_targets()

    def _delete_account_target(self, target: AccountTargetRow) -> None:
        if QMessageBox.question(
            self, "Confirm", f"Delete account target '{target.account_name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) == QMessageBox.StandardButton.Yes:
            delete_account_target(self.app_state.conn, target.id)
            self._refresh_account_targets()
