"""
Settings: folder rules, statuses, account targets (PluginData).
"""

from __future__ import annotations

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
)
from PySide6.QtCore import Qt

from ..services.app_state import AppState
from ..services.preferences import (
    get_default_status_id,
    set_default_status_id,
    get_base_font_size,
    set_base_font_size,
)
from ..db import list_folder_rules, add_folder_rule, update_folder_rule, delete_folder_rule, FolderRuleRow, RuleType
from ..db.status_repo import list_statuses, add_status, update_status, delete_status, StatusRow
from ..db.account_target import list_account_targets, add_account_target, update_account_target, delete_account_target, AccountTargetRow


class FolderRuleEditor(QDialog):
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


class StatusEditor(QDialog):
    def __init__(self, parent: QWidget | None, status: StatusRow | None = None) -> None:
        super().__init__(parent)
        self.status = status
        self.setWindowTitle("Edit status" if status else "Add status")
        layout = QFormLayout(self)
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("e.g. New, Ready")
        self.color_edit = QLineEdit()
        self.color_edit.setPlaceholderText("#RRGGBB or leave empty for theme default")
        self.enabled_check = QCheckBox("Active")
        self.enabled_check.setChecked(True)
        self.sort_spin = QSpinBox()
        self.sort_spin.setRange(-1000, 1000)
        self.sort_spin.setSpecialValueText("—")
        layout.addRow("Name:", self.name_edit)
        layout.addRow("Color (hex):", self.color_edit)
        layout.addRow("", self.enabled_check)
        layout.addRow("Sort order:", self.sort_spin)
        if status:
            self.name_edit.setText(status.name)
            self.color_edit.setText(status.color or "")
            self.enabled_check.setChecked(status.is_active)
            self.sort_spin.setValue(status.sort_order if status.sort_order is not None else 0)
        ok = QPushButton("OK")
        ok.clicked.connect(self.accept)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        layout.addRow(ok, cancel)

    def get_values(self) -> tuple[str, str | None, bool, int | None]:
        color = self.color_edit.text().strip() or None
        sort_order = self.sort_spin.value()
        return (
            self.name_edit.text().strip(),
            color,
            self.enabled_check.isChecked(),
            sort_order,
        )


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
        self.tabs.addTab(self._build_folder_rules_tab(), "Folder rules")
        self.tabs.addTab(self._build_statuses_tab(), "Statuses")
        self.tabs.addTab(self._build_account_targets_tab(), "Account targets")
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
        self.folder_table = QTableWidget()
        self.folder_table.setColumnCount(4)
        self.folder_table.setHorizontalHeaderLabels(["Type", "Path", "Enabled", "Actions"])
        self.folder_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        v.addWidget(self.folder_table)
        add_btn = QPushButton("Add folder rule")
        add_btn.clicked.connect(self._add_folder_rule)
        v.addWidget(add_btn)
        self._refresh_folder_rules()
        return w

    def _refresh_folder_rules(self) -> None:
        rules = list_folder_rules(self.app_state.conn)
        self.folder_table.setRowCount(len(rules))
        for i, r in enumerate(rules):
            self.folder_table.setItem(i, 0, QTableWidgetItem(r.rule_type))
            self.folder_table.setItem(i, 1, QTableWidgetItem(r.path))
            self.folder_table.setItem(i, 2, QTableWidgetItem("Yes" if r.enabled else "No"))
            btn = QPushButton("Edit")
            btn.setProperty("rule_id", r.id)
            btn.clicked.connect(lambda checked=False, row=r: self._edit_folder_rule(row))
            del_btn = QPushButton("Delete")
            del_btn.setProperty("rule_id", r.id)
            del_btn.clicked.connect(lambda checked=False, row=r: self._delete_folder_rule(row))
            cell = QWidget()
            cell_layout = QHBoxLayout(cell)
            cell_layout.addWidget(btn)
            cell_layout.addWidget(del_btn)
            self.folder_table.setCellWidget(i, 3, cell)
        self.folder_table.setRowCount(len(rules))

    def _add_folder_rule(self) -> None:
        dlg = FolderRuleEditor(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            rule_type, path, enabled = dlg.get_values()
            if not path:
                QMessageBox.warning(self, "Error", "Path is required.")
                return
            add_folder_rule(self.app_state.conn, rule_type, path, enabled)
            self._refresh_folder_rules()

    def _edit_folder_rule(self, rule: FolderRuleRow) -> None:
        dlg = FolderRuleEditor(self, rule)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            rule_type, path, enabled = dlg.get_values()
            if not path:
                QMessageBox.warning(self, "Error", "Path is required.")
                return
            update_folder_rule(self.app_state.conn, rule.id, path=path, enabled=enabled)
            self._refresh_folder_rules()

    def _delete_folder_rule(self, rule: FolderRuleRow) -> None:
        if QMessageBox.question(
            self, "Confirm", f"Delete folder rule: {rule.rule_type} — {rule.path}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) == QMessageBox.StandardButton.Yes:
            delete_folder_rule(self.app_state.conn, rule.id)
            self._refresh_folder_rules()

    def _build_statuses_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        default_row = QHBoxLayout()
        default_row.addWidget(QLabel("Default status (Library):"))
        self.default_status_combo = QComboBox()
        self.default_status_combo.setMinimumWidth(140)
        default_row.addWidget(self.default_status_combo)
        default_row.addStretch()
        v.addLayout(default_row)
        self.status_table = QTableWidget()
        self.status_table.setColumnCount(5)
        self.status_table.setHorizontalHeaderLabels(["Name", "Color", "Active", "Sort", "Actions"])
        v.addWidget(self.status_table)
        add_btn = QPushButton("Add status")
        add_btn.clicked.connect(self._add_status)
        v.addWidget(add_btn)
        self._refresh_statuses()
        self._load_default_status_combo()
        self.default_status_combo.currentIndexChanged.connect(self._on_default_status_changed)
        return w

    def _load_default_status_combo(self) -> None:
        from PySide6.QtCore import QSignalBlocker
        with QSignalBlocker(self.default_status_combo):
            self.default_status_combo.clear()
            self.default_status_combo.addItem("(none)", None)
            for r in list_statuses(self.app_state.conn):
                self.default_status_combo.addItem(r.name, r.id)
            current = get_default_status_id()
            idx = self.default_status_combo.findData(current)
            if idx >= 0:
                self.default_status_combo.setCurrentIndex(idx)
            else:
                self.default_status_combo.setCurrentIndex(0)

    def _on_default_status_changed(self) -> None:
        data = self.default_status_combo.currentData()
        set_default_status_id(data)

    def _refresh_statuses(self) -> None:
        rows = list_statuses(self.app_state.conn)
        self.status_table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            self.status_table.setItem(i, 0, QTableWidgetItem(r.name))
            self.status_table.setItem(i, 1, QTableWidgetItem(r.color or "(theme)"))
            self.status_table.setItem(i, 2, QTableWidgetItem("Yes" if r.is_active else "No"))
            self.status_table.setItem(i, 3, QTableWidgetItem(str(r.sort_order) if r.sort_order is not None else "—"))
            edit_btn = QPushButton("Edit")
            edit_btn.clicked.connect(lambda checked=False, row=r: self._edit_status(row))
            del_btn = QPushButton("Delete")
            del_btn.clicked.connect(lambda checked=False, row=r: self._delete_status(row))
            cell = QWidget()
            cell_layout = QHBoxLayout(cell)
            cell_layout.addWidget(edit_btn)
            cell_layout.addWidget(del_btn)
            self.status_table.setCellWidget(i, 4, cell)
        self.status_table.setRowCount(len(rows))
        self._load_default_status_combo()

    def _add_status(self) -> None:
        dlg = StatusEditor(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            name, color, is_active, sort_order = dlg.get_values()
            if not name:
                QMessageBox.warning(self, "Error", "Name is required.")
                return
            add_status(self.app_state.conn, name, color=color, is_active=is_active, sort_order=sort_order)
            self._refresh_statuses()

    def _edit_status(self, status: StatusRow) -> None:
        dlg = StatusEditor(self, status)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            name, color, is_active, sort_order = dlg.get_values()
            if not name:
                QMessageBox.warning(self, "Error", "Name is required.")
                return
            update_status(self.app_state.conn, status.id, name=name, color=color, is_active=is_active, sort_order=sort_order)
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
        self.account_table = QTableWidget()
        self.account_table.setColumnCount(4)
        self.account_table.setHorizontalHeaderLabels(["Account", "Path", "Enabled", "Actions"])
        self.account_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        v.addWidget(self.account_table)
        add_btn = QPushButton("Add account target")
        add_btn.clicked.connect(self._add_account_target)
        v.addWidget(add_btn)
        self._refresh_account_targets()
        return w

    def _refresh_account_targets(self) -> None:
        rows = list_account_targets(self.app_state.conn)
        self.account_table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            self.account_table.setItem(i, 0, QTableWidgetItem(r.account_name))
            self.account_table.setItem(i, 1, QTableWidgetItem(r.plugin_data_path))
            self.account_table.setItem(i, 2, QTableWidgetItem("Yes" if r.enabled else "No"))
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
