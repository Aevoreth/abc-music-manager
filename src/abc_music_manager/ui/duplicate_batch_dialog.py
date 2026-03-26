"""
Batch duplicate review: one dialog for all primary-library identity collisions after scan.
Grouped by folder; bulk actions; per-row resolution with diff (shared with single-file flow).
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTextBrowser,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..db.library_query import get_primary_file_path_for_song
from ..scanning.duplicate_types import DuplicateCandidate, DuplicateDecision
from .duplicate_ui_common import make_split_diff_html, path_for_display

ROLE_CANDIDATE_INDEX = Qt.ItemDataRole.UserRole
ROLE_FOLDER_PATH = Qt.ItemDataRole.UserRole + 1


def show_batch_duplicate_review(
    conn,
    candidates: list[DuplicateCandidate],
) -> list[DuplicateDecision] | None:
    """Show batch dialog. Returns decisions in candidate order, or None if cancelled."""
    dlg = DuplicateBatchDialog(conn, candidates)
    if dlg.exec() != QDialog.DialogCode.Accepted:
        return None
    return dlg.get_decisions()


def _action_label(action: str) -> str:
    return {
        "keep_existing": "Ignore new",
        "keep_existing_delete_new": "Keep existing, deleted new",
        "keep_new": "Keep new",
        "keep_new_delete_existing": "Keep new, deleted old",
        "separate": "Separate entry",
        "ignore": "Ignore new",
    }.get(action, action)


class DuplicateBatchDialog(QDialog):
    def __init__(self, conn, candidates: list[DuplicateCandidate]) -> None:
        super().__init__()
        self.conn = conn
        self.candidates = candidates
        self._n = len(candidates)
        # Resolved[i] = None (pending) or (action, existing_song_id)
        self._resolved: list[tuple[str, int | None] | None] = [None] * self._n
        self._existing_pick: dict[int, int] = {}

        self.setWindowTitle("Duplicate songs — batch review")
        self.setMinimumSize(1000, 700)
        self.resize(1100, 750)

        root_layout = QVBoxLayout(self)
        root_layout.addWidget(QLabel(
            "These new files match existing songs (same title, composer, part count). "
            "Choose a resolution for each, or use bulk actions by folder. OK requires every row to be resolved."
        ))

        toolbar = QHBoxLayout()
        self.separate_all_btn = QPushButton("Separate all pending")
        self.separate_all_btn.clicked.connect(self._separate_all_pending)
        toolbar.addWidget(self.separate_all_btn)
        self.separate_folder_btn = QPushButton("Separate all in selected folder")
        self.separate_folder_btn.clicked.connect(self._separate_selected_folder)
        toolbar.addWidget(self.separate_folder_btn)
        self.ignore_folder_btn = QPushButton("Ignore all new in selected folder")
        self.ignore_folder_btn.clicked.connect(self._ignore_new_in_selected_folder)
        toolbar.addWidget(self.ignore_folder_btn)
        toolbar.addStretch()
        root_layout.addLayout(toolbar)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Item", "Resolution"])
        self.tree.setMinimumWidth(360)
        self.tree.itemSelectionChanged.connect(self._on_tree_selection)
        splitter.addWidget(self.tree)

        detail = QWidget()
        detail_layout = QVBoxLayout(detail)

        self.detail_title = QLabel()
        self.detail_title.setWordWrap(True)
        detail_layout.addWidget(self.detail_title)

        paths_row = QHBoxLayout()
        self.left_path_label = QLabel()
        self.left_path_label.setWordWrap(True)
        self.right_path_label = QLabel()
        self.right_path_label.setWordWrap(True)
        paths_row.addWidget(self.left_path_label, 1)
        paths_row.addWidget(self.right_path_label, 1)
        detail_layout.addLayout(paths_row)

        self.existing_combo_label = QLabel("Compare with existing:")
        detail_layout.addWidget(self.existing_combo_label)
        self.existing_combo = QComboBox()
        self.existing_combo.currentIndexChanged.connect(self._on_existing_combo_changed)
        detail_layout.addWidget(self.existing_combo)

        self.diff_browser = QTextBrowser()
        self.diff_browser.setOpenExternalLinks(False)
        self.diff_browser.setMinimumHeight(260)
        detail_layout.addWidget(self.diff_browser, stretch=1)

        actions_layout = QHBoxLayout()
        left_frame = QFrame()
        left_frame.setFrameStyle(QFrame.StyledPanel | QFrame.Plain)
        left_layout = QVBoxLayout(left_frame)
        left_layout.addWidget(QLabel("Keep existing file:"))
        b1 = QPushButton("Keep this version")
        b1.clicked.connect(lambda: self._apply_selected("keep_existing"))
        left_layout.addWidget(b1)
        b2 = QPushButton("Keep this & delete new (→ Recycle Bin)")
        b2.clicked.connect(lambda: self._apply_selected("keep_existing_delete_new"))
        left_layout.addWidget(b2)
        actions_layout.addWidget(left_frame)

        mid_frame = QFrame()
        mid_frame.setFrameStyle(QFrame.StyledPanel | QFrame.Plain)
        mid_layout = QVBoxLayout(mid_frame)
        mid_layout.addWidget(QLabel("Keep both:"))
        b3 = QPushButton("Create separate entry")
        b3.clicked.connect(lambda: self._apply_selected("separate"))
        mid_layout.addWidget(b3)
        actions_layout.addWidget(mid_frame)

        right_frame = QFrame()
        right_frame.setFrameStyle(QFrame.StyledPanel | QFrame.Plain)
        right_layout = QVBoxLayout(right_frame)
        right_layout.addWidget(QLabel("Keep new file:"))
        b4 = QPushButton("Keep this version")
        b4.clicked.connect(lambda: self._apply_selected("keep_new"))
        right_layout.addWidget(b4)
        b5 = QPushButton("Keep this & delete existing (→ Recycle Bin)")
        b5.clicked.connect(lambda: self._apply_selected("keep_new_delete_existing"))
        right_layout.addWidget(b5)
        actions_layout.addWidget(right_frame)

        detail_layout.addLayout(actions_layout)

        splitter.addWidget(detail)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        root_layout.addWidget(splitter, stretch=1)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.ok_btn = QPushButton("OK")
        self.ok_btn.setEnabled(False)
        self.ok_btn.clicked.connect(self._on_ok)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(self.ok_btn)
        root_layout.addLayout(btn_row)

        self._build_tree()
        self._refresh_detail()

    def _build_tree(self) -> None:
        self.tree.clear()
        by_folder: dict[str, list[int]] = defaultdict(list)
        for i, c in enumerate(self.candidates):
            by_folder[str(Path(c.new_path).parent)].append(i)

        for folder in sorted(by_folder.keys(), key=str.lower):
            folder_item = QTreeWidgetItem([path_for_display(folder), ""])
            folder_item.setData(0, ROLE_FOLDER_PATH, folder)
            folder_item.setFlags(folder_item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            self.tree.addTopLevelItem(folder_item)
            for idx in by_folder[folder]:
                c = self.candidates[idx]
                leaf = QTreeWidgetItem([f"{c.parsed.title} — {Path(c.new_path).name}", "Pending"])
                leaf.setData(0, ROLE_CANDIDATE_INDEX, idx)
                folder_item.addChild(leaf)
        self.tree.expandAll()
        self.tree.resizeColumnToContents(0)

    def _current_candidate_index(self) -> int | None:
        items = self.tree.selectedItems()
        if not items:
            return None
        idx = items[0].data(0, ROLE_CANDIDATE_INDEX)
        if idx is None:
            return None
        return int(idx)

    def _selected_folder_path(self) -> str | None:
        items = self.tree.selectedItems()
        if not items:
            return None
        it = items[0]
        p = it.data(0, ROLE_FOLDER_PATH)
        if p is not None:
            return str(p)
        parent = it.parent()
        if parent is not None:
            pp = parent.data(0, ROLE_FOLDER_PATH)
            if pp is not None:
                return str(pp)
        return None

    def _indices_in_folder(self, folder: str) -> list[int]:
        out: list[int] = []
        for i, c in enumerate(self.candidates):
            if str(Path(c.new_path).parent) == folder:
                out.append(i)
        return out

    def _on_tree_selection(self) -> None:
        self._refresh_detail()

    def _refresh_detail(self) -> None:
        idx = self._current_candidate_index()
        self.existing_combo.blockSignals(True)
        self.existing_combo.clear()
        self.existing_combo_label.setVisible(False)
        self.existing_combo.setVisible(False)

        if idx is None:
            self.detail_title.setText("Select a song under a folder to compare and resolve.")
            self.left_path_label.setText("")
            self.right_path_label.setText("")
            self.diff_browser.clear()
            self.existing_combo.blockSignals(False)
            return

        c = self.candidates[idx]
        self.detail_title.setText(
            f"<b>{c.parsed.title}</b> — composer: {c.parsed.composers or '(none)'} — "
            f"{len(c.parsed.parts)} part(s)"
        )
        self.right_path_label.setText(f"<b>New:</b> {path_for_display(c.new_path)}")

        for sid in c.existing_song_ids:
            path = get_primary_file_path_for_song(self.conn, sid) or f"(unknown #{sid})"
            self.existing_combo.addItem(f"#{sid} — {path_for_display(path)}", sid)

        pick = self._existing_pick.get(idx)
        if pick is None or pick not in c.existing_song_ids:
            pick = c.existing_song_ids[0] if c.existing_song_ids else None
        if pick is not None:
            for j in range(self.existing_combo.count()):
                if self.existing_combo.itemData(j) == pick:
                    self.existing_combo.setCurrentIndex(j)
                    break

        show_combo = len(c.existing_song_ids) > 1
        self.existing_combo_label.setVisible(show_combo)
        self.existing_combo.setVisible(show_combo)

        self._refresh_diff_for(idx)
        self.existing_combo.blockSignals(False)

    def _existing_song_id_for_ui(self) -> int | None:
        idx = self._current_candidate_index()
        if idx is None:
            return None
        c = self.candidates[idx]
        if not c.existing_song_ids:
            return None
        data = self.existing_combo.currentData()
        if data is not None:
            return int(data)
        return c.existing_song_ids[0]

    def _on_existing_combo_changed(self) -> None:
        idx = self._current_candidate_index()
        if idx is None:
            return
        sid = self._existing_song_id_for_ui()
        if sid is not None:
            self._existing_pick[idx] = sid
        self._refresh_diff_for(idx)

    def _refresh_diff_for(self, idx: int) -> None:
        c = self.candidates[idx]
        sid = self._existing_pick.get(idx)
        if sid is None or sid not in c.existing_song_ids:
            sid = c.existing_song_ids[0] if c.existing_song_ids else None
        if sid is None:
            self.left_path_label.setText("<b>Existing:</b> (none)")
            self.diff_browser.setHtml("<body><p>No existing song selected.</p></body>")
            return
        existing_path = get_primary_file_path_for_song(self.conn, sid) or "(unknown)"
        self.left_path_label.setText(f"<b>Existing:</b> {path_for_display(existing_path)}")
        self.diff_browser.setHtml(make_split_diff_html(existing_path, c.new_path))

    def _update_tree_status_for_index(self, idx: int) -> None:
        r = self._resolved[idx]
        text = "Pending" if r is None else _action_label(r[0])
        root = self.tree.invisibleRootItem()
        for i in range(root.childCount()):
            folder_item = root.child(i)
            for j in range(folder_item.childCount()):
                leaf = folder_item.child(j)
                if leaf.data(0, ROLE_CANDIDATE_INDEX) == idx:
                    leaf.setText(1, text)
                    return

    def _apply_selected(self, action: str) -> None:
        idx = self._current_candidate_index()
        if idx is None:
            return
        c = self.candidates[idx]
        sid: int | None
        if action == "separate":
            sid = None
        else:
            sid = self._existing_song_id_for_ui()
            if sid is None and c.existing_song_ids:
                sid = c.existing_song_ids[0]
        self._resolved[idx] = (action, sid)
        self._update_tree_status_for_index(idx)
        self._refresh_ok()

    def _set_indices(self, indices: list[int], action: str, existing_id: int | None) -> None:
        for idx in indices:
            c = self.candidates[idx]
            sid = existing_id
            if action != "separate" and sid is None and c.existing_song_ids:
                sid = c.existing_song_ids[0]
            self._resolved[idx] = (action, sid)
            self._update_tree_status_for_index(idx)
        self._refresh_ok()

    def _separate_all_pending(self) -> None:
        pending = [i for i in range(self._n) if self._resolved[i] is None]
        self._set_indices(pending, "separate", None)

    def _separate_selected_folder(self) -> None:
        folder = self._selected_folder_path()
        if not folder:
            QMessageBox.information(self, "Batch duplicates", "Select a folder or a song under a folder first.")
            return
        idxs = [i for i in self._indices_in_folder(folder) if self._resolved[i] is None]
        if not idxs:
            QMessageBox.information(self, "Batch duplicates", "No pending items in that folder.")
            return
        self._set_indices(idxs, "separate", None)

    def _ignore_new_in_selected_folder(self) -> None:
        folder = self._selected_folder_path()
        if not folder:
            QMessageBox.information(self, "Batch duplicates", "Select a folder or a song under a folder first.")
            return
        idxs = self._indices_in_folder(folder)
        pending = [i for i in idxs if self._resolved[i] is None]
        if not pending:
            QMessageBox.information(self, "Batch duplicates", "No pending items in that folder.")
            return
        reply = QMessageBox.question(
            self,
            "Ignore all new in folder",
            f"Mark {len(pending)} pending file(s) under {path_for_display(folder)} as ignored "
            "(existing library entry kept; new file not indexed)?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        for i in pending:
            c = self.candidates[i]
            sid = c.existing_song_ids[0] if c.existing_song_ids else None
            self._resolved[i] = ("keep_existing", sid)
            self._update_tree_status_for_index(i)
        self._refresh_ok()

    def _refresh_ok(self) -> None:
        self.ok_btn.setEnabled(all(self._resolved[i] is not None for i in range(self._n)))

    def _on_ok(self) -> None:
        if not all(self._resolved[i] is not None for i in range(self._n)):
            return
        self.accept()

    def get_decisions(self) -> list[DuplicateDecision]:
        out: list[DuplicateDecision] = []
        for i, c in enumerate(self.candidates):
            r = self._resolved[i]
            assert r is not None
            action, sid = r
            out.append(DuplicateDecision(new_path=c.new_path, action=action, existing_song_id=sid))
        return out
