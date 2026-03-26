"""
Duplicate resolution dialog: when two primary-library files share logical identity.
Shows side-by-side diff with red/green highlighting. Options: keep either version,
keep and delete the other (to recycle bin), or create separate entries.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextBrowser,
    QFrame,
)

from ..db.library_query import get_primary_file_path_for_song
from .duplicate_ui_common import make_split_diff_html, path_for_display


# Result: (action, existing_song_id | None)
# Actions: "keep_existing", "keep_existing_delete_new", "keep_new"
# "keep_new_delete_existing", "separate", "ignore"
DuplicateResolutionResult = tuple[str, int | None]


def show_duplicate_resolution(
    conn,
    new_file_path: str,
    parsed_title: str,
    existing_song_ids: list[int],
) -> DuplicateResolutionResult:
    """
    Show dialog with diff view. Returns (action, existing_song_id).
    Actions: keep_existing, keep_existing_delete_new, keep_new, keep_new_delete_existing, separate, ignore.
    """
    dlg = DuplicateResolutionDialog(conn, new_file_path, parsed_title, existing_song_ids)
    if dlg.exec() != QDialog.DialogCode.Accepted:
        return ("ignore", None)
    return dlg.get_result()


class DuplicateResolutionDialog(QDialog):
    def __init__(
        self,
        conn,
        new_file_path: str,
        parsed_title: str,
        existing_song_ids: list[int],
    ) -> None:
        super().__init__()
        self.conn = conn
        self.new_file_path = new_file_path
        self.existing_song_ids = existing_song_ids
        self._result: DuplicateResolutionResult = ("ignore", None)

        existing_song_id = existing_song_ids[0] if existing_song_ids else None
        existing_path = (
            get_primary_file_path_for_song(conn, existing_song_id) or "(unknown)"
            if existing_song_id
            else "(unknown)"
        )

        self.setWindowTitle("Duplicate song detected")
        self.setMinimumSize(900, 600)
        self.resize(1000, 700)

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel(
            "Two files have the same identity (title, composer, part count). "
            "Compare them below and choose how to resolve."
        ))

        existing_display = path_for_display(existing_path)
        new_display = path_for_display(new_file_path)
        paths_layout = QHBoxLayout()
        existing_label = QLabel(f"<b>Existing:</b> {existing_display}")
        existing_label.setWordWrap(True)
        paths_layout.addWidget(existing_label, 1)
        new_label = QLabel(f"<b>New:</b> {new_display}")
        new_label.setWordWrap(True)
        paths_layout.addWidget(new_label, 1)
        layout.addLayout(paths_layout)

        diff_html = make_split_diff_html(existing_path, new_file_path)
        diff_browser = QTextBrowser()
        diff_browser.setOpenExternalLinks(False)
        diff_browser.setHtml(diff_html)
        diff_browser.setMinimumHeight(300)
        layout.addWidget(diff_browser, stretch=1)

        actions_layout = QHBoxLayout()

        left_frame = QFrame()
        left_frame.setFrameStyle(QFrame.StyledPanel | QFrame.Plain)
        left_layout = QVBoxLayout(left_frame)
        left_layout.addWidget(QLabel("Keep existing file:"))
        keep_existing_btn = QPushButton("Keep this version")
        keep_existing_btn.clicked.connect(lambda: self._accept_result("keep_existing", existing_song_id))
        left_layout.addWidget(keep_existing_btn)
        keep_existing_del_btn = QPushButton("Keep this & delete new (→ Recycle Bin)")
        keep_existing_del_btn.clicked.connect(
            lambda: self._accept_result("keep_existing_delete_new", existing_song_id)
        )
        left_layout.addWidget(keep_existing_del_btn)
        actions_layout.addWidget(left_frame)

        middle_frame = QFrame()
        middle_frame.setFrameStyle(QFrame.StyledPanel | QFrame.Plain)
        middle_layout = QVBoxLayout(middle_frame)
        middle_layout.addWidget(QLabel("Keep both:"))
        separate_btn = QPushButton("Create separate entry")
        separate_btn.clicked.connect(lambda: self._accept_result("separate", None))
        middle_layout.addWidget(separate_btn)
        actions_layout.addWidget(middle_frame)

        right_frame = QFrame()
        right_frame.setFrameStyle(QFrame.StyledPanel | QFrame.Plain)
        right_layout = QVBoxLayout(right_frame)
        right_layout.addWidget(QLabel("Keep new file:"))
        keep_new_btn = QPushButton("Keep this version")
        keep_new_btn.clicked.connect(lambda: self._accept_result("keep_new", existing_song_id))
        right_layout.addWidget(keep_new_btn)
        keep_new_del_btn = QPushButton("Keep this & delete existing (→ Recycle Bin)")
        keep_new_del_btn.clicked.connect(
            lambda: self._accept_result("keep_new_delete_existing", existing_song_id)
        )
        right_layout.addWidget(keep_new_del_btn)
        actions_layout.addWidget(right_frame)

        layout.addLayout(actions_layout)

        cancel_btn = QPushButton("Cancel (ignore new file)")
        cancel_btn.clicked.connect(self.reject)
        layout.addWidget(cancel_btn)

    def _accept_result(self, action: str, existing_song_id: int | None) -> None:
        self._result = (action, existing_song_id)
        self.accept()

    def get_result(self) -> DuplicateResolutionResult:
        return self._result
