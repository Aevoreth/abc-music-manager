"""
UI to resolve duplicate folder structures: pick folder to keep, unindex or trash others.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..scanning.folder_duplicate_apply import (
    FolderClusterApply,
    LoseDisposition,
    apply_folder_cluster_resolutions,
)
from ..scanning.folder_duplicate_detect import FolderDuplicateCluster
from .duplicate_ui_common import path_for_display


class FolderDuplicateDialog(QDialog):
    def __init__(
        self,
        parent: QWidget | None,
        conn,
        clusters: list[FolderDuplicateCluster],
        *,
        pending_file_duplicates: int = 0,
    ) -> None:
        super().__init__(parent)
        self.conn = conn
        self.clusters = clusters
        self._applied_losing_roots: set[str] = set()

        self.setWindowTitle("Duplicate folder structures")
        self.setMinimumSize(720, 520)
        self.resize(900, 640)

        layout = QVBoxLayout(self)
        intro = (
            "These folders have the same relative .abc layout and the same song identity per file. "
            "Pick one folder to keep. For each other folder, choose whether to remove it from the library only "
            "(files stay on disk) or move it to the Recycle Bin."
        )
        if pending_file_duplicates:
            intro += (
                f"\n\nAfter you apply, up to {pending_file_duplicates} file-level duplicate(s) under removed "
                "folders may be skipped automatically."
            )
        layout.addWidget(QLabel(intro))

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        self._clusters_layout = QVBoxLayout(inner)
        self._cluster_widgets: list[_ClusterPanel]=[]
        for i, cl in enumerate(clusters):
            panel = _ClusterPanel(i + 1, cl)
            self._cluster_widgets.append(panel)
            self._clusters_layout.addWidget(panel)
        self._clusters_layout.addStretch()
        scroll.setWidget(inner)
        layout.addWidget(scroll, stretch=1)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = QPushButton("Skip")
        cancel_btn.clicked.connect(self.reject)
        apply_btn = QPushButton("Apply")
        apply_btn.clicked.connect(self._on_apply)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(apply_btn)
        layout.addLayout(btn_row)

    def _on_apply(self) -> None:
        resolutions: list[FolderClusterApply] = []
        for panel in self._cluster_widgets:
            resolutions.append(panel.build_resolution())

        any_trash = any(
            disp == "trash"
            for r in resolutions
            for _p, disp in r.losers
        )
        if any_trash:
            reply = QMessageBox.question(
                self,
                "Move folders to Recycle Bin",
                "Some folders will be moved to the Recycle Bin (including their .abc files). Continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        losing, errors = apply_folder_cluster_resolutions(self.conn, resolutions)
        self._applied_losing_roots = losing
        if errors:
            QMessageBox.warning(
                self,
                "Duplicate folders",
                "Applied with warnings:\n" + "\n".join(errors[:15])
                + ("\n…" if len(errors) > 15 else ""),
            )
        self.accept()

    def get_applied_losing_roots(self) -> set[str]:
        return set(self._applied_losing_roots)


class _ClusterPanel(QFrame):
    def __init__(self, index: int, cluster: FolderDuplicateCluster) -> None:
        super().__init__()
        self.cluster = cluster
        self.setFrameStyle(QFrame.StyledPanel | QFrame.Plain)
        outer = QVBoxLayout(self)
        roots = list(cluster.root_paths)
        samples = ", ".join(cluster.sample_titles) if cluster.sample_titles else "—"
        outer.addWidget(QLabel(
            f"<b>Cluster {index}</b> — {len(roots)} folders, ~{cluster.file_count} .abc file(s) in each. "
            f"Examples: {samples}"
        ))

        outer.addWidget(QLabel("<b>Keep this folder (library + disk unchanged for this copy):</b>"))
        self._keep_group = QButtonGroup(self)
        self._keep_radios: dict[str, QRadioButton] = {}
        default_keep = sorted(roots, key=str.lower)[0]
        for r in sorted(roots, key=str.lower):
            rb = QRadioButton(path_for_display(r))
            self._keep_group.addButton(rb)
            self._keep_radios[r] = rb
            if r == default_keep:
                rb.setChecked(True)
            outer.addWidget(rb)

        outer.addWidget(QLabel("<b>For each folder you are not keeping:</b>"))
        self._lose_combos: dict[str, QComboBox] = {}
        self._lose_rows: dict[str, QWidget] = {}
        for r in sorted(roots, key=str.lower):
            row_w = QWidget()
            row = QHBoxLayout(row_w)
            row.setContentsMargins(0, 0, 0, 0)
            row.addWidget(QLabel(path_for_display(r)), stretch=1)
            cb = QComboBox()
            cb.addItem("Remove from library only", "unindex")
            cb.addItem("Move folder to Recycle Bin", "trash")
            self._lose_combos[r] = cb
            row.addWidget(cb)
            self._lose_rows[r] = row_w
            outer.addWidget(row_w)

        self._keep_group.buttonClicked.connect(self._refresh_lose_rows)
        self._refresh_lose_rows()

    def _refresh_lose_rows(self) -> None:
        keep = self._selected_keep_root()
        for r, w in self._lose_rows.items():
            w.setVisible(r != keep)

    def _selected_keep_root(self) -> str:
        for r, rb in self._keep_radios.items():
            if rb.isChecked():
                return r
        return self.cluster.root_paths[0]

    def build_resolution(self) -> FolderClusterApply:
        keep = self._selected_keep_root()
        losers: list[tuple[str, LoseDisposition]] = []
        for r in self.cluster.root_paths:
            if r == keep:
                continue
            cb = self._lose_combos[r]
            disp = cb.currentData()
            assert disp in ("unindex", "trash")
            losers.append((r, disp))
        return FolderClusterApply(keep_root=keep, losers=losers)


def show_folder_duplicate_dialog_for_scan(
    parent: QWidget | None,
    conn,
    clusters: list[FolderDuplicateCluster],
    pending_count: int,
) -> set[str]:
    """
    Modal dialog during scan. Returns normalized paths of folders unindexed/trashed.
    Skip/Cancel returns empty set (no folder changes).
    """
    dlg = FolderDuplicateDialog(parent, conn, clusters, pending_file_duplicates=pending_count)
    if dlg.exec() != QDialog.DialogCode.Accepted:
        return set()
    return dlg.get_applied_losing_roots()


def show_standalone_folder_duplicate_dialog(
    parent: QWidget | None,
    conn,
    clusters: list[FolderDuplicateCluster],
) -> None:
    """Analyze menu: show dialog; Skip closes without DB/disk changes."""
    dlg = FolderDuplicateDialog(parent, conn, clusters, pending_file_duplicates=0)
    dlg.exec()
