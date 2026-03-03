"""
Duplicate resolution dialog: when two primary-library files share logical identity.
Shows side-by-side diff with red/green highlighting. Options: keep either version,
keep and delete the other (to recycle bin), or create separate entries.
"""

from __future__ import annotations

import difflib
from pathlib import Path

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
from ..services.preferences import to_music_relative


# Result: (action, existing_song_id | None)
# Actions: "keep_existing", "keep_existing_delete_new", "keep_new", "keep_new_delete_existing", "separate", "ignore"
DuplicateResolutionResult = tuple[str, int | None]


def _path_for_display(path: str) -> str:
    """Return path relative to Music directory for display, or full path if outside Music."""
    if not path or path.startswith("("):
        return path
    rel = to_music_relative(path)
    return rel if rel else path


def _read_file_content(path: str) -> str:
    """Read file content, or return error message."""
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return f"# Error reading file: {e}"


def _html_escape(s: str) -> str:
    """Escape HTML special characters."""
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _make_split_diff_html(
    left_path: str, right_path: str
) -> str:
    """
    Generate HTML for side-by-side diff with equal 50/50 columns.
    Left: existing file (red for removed). Right: new file (green for added).
    """
    if left_path.startswith("(") or not Path(left_path).is_file():
        left_lines = [f"# File not found: {left_path}"]
    else:
        left_lines = _read_file_content(left_path).splitlines()
    if right_path.startswith("(") or not Path(right_path).is_file():
        right_lines = [f"# File not found: {right_path}"]
    else:
        right_lines = _read_file_content(right_path).splitlines()
    if not left_lines:
        left_lines = [""]
    if not right_lines:
        right_lines = [""]

    matcher = difflib.SequenceMatcher(None, left_lines, right_lines)
    rows: list[tuple[str, str, str, str]] = []  # (left_cell, right_cell, left_class, right_class)
    left_ln = 1
    right_ln = 1

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for i, j in zip(range(i1, i2), range(j1, j2)):
                rows.append((
                    f"{left_ln} {_html_escape(left_lines[i])}",
                    f"{right_ln} {_html_escape(right_lines[j])}",
                    "",
                    "",
                ))
                left_ln += 1
                right_ln += 1
        elif tag == "replace":
            left_chunk = list(range(i1, i2))
            right_chunk = list(range(j1, j2))
            for k in range(max(len(left_chunk), len(right_chunk))):
                left_text = f"{left_ln} {_html_escape(left_lines[left_chunk[k]])}" if k < len(left_chunk) else ""
                right_text = f"{right_ln} {_html_escape(right_lines[right_chunk[k]])}" if k < len(right_chunk) else ""
                left_cl = "removed" if k < len(left_chunk) else ""
                right_cl = "added" if k < len(right_chunk) else ""
                rows.append((left_text, right_text, left_cl, right_cl))
                if k < len(left_chunk):
                    left_ln += 1
                if k < len(right_chunk):
                    right_ln += 1
        elif tag == "delete":
            for i in range(i1, i2):
                rows.append((
                    f"{left_ln} {_html_escape(left_lines[i])}",
                    "",
                    "removed",
                    "",
                ))
                left_ln += 1
        elif tag == "insert":
            for j in range(j1, j2):
                rows.append((
                    "",
                    f"{right_ln} {_html_escape(right_lines[j])}",
                    "",
                    "added",
                ))
                right_ln += 1

    trs = "".join(
        f'<tr><td class="{lc}">{left or "&nbsp;"}</td><td class="{rc}">{right or "&nbsp;"}</td></tr>'
        for left, right, lc, rc in rows
    )
    style = """
    <style>
        table.diff { font-family: monospace; font-size: 12px; width: 100%; table-layout: fixed; }
        table.diff td { vertical-align: top; padding: 2px 6px; white-space: pre-wrap; word-wrap: break-word; }
        .removed { background-color: #5c2a2a !important; }
        .added { background-color: #2a5c2a !important; }
    </style>
    """
    return style + "<body><table class='diff'><colgroup><col width='50%'/><col width='50%'/></colgroup><tbody>" + trs + "</tbody></table></body>"


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

        # Path labels above diff — split evenly, each wraps within its half
        existing_display = _path_for_display(existing_path)
        new_display = _path_for_display(new_file_path)
        paths_layout = QHBoxLayout()
        existing_label = QLabel(f"<b>Existing:</b> {existing_display}")
        existing_label.setWordWrap(True)
        paths_layout.addWidget(existing_label, 1)
        new_label = QLabel(f"<b>New:</b> {new_display}")
        new_label.setWordWrap(True)
        paths_layout.addWidget(new_label, 1)
        layout.addLayout(paths_layout)

        # Diff view — spans full width, evenly split 50/50 columns
        diff_html = _make_split_diff_html(existing_path, new_file_path)
        diff_browser = QTextBrowser()
        diff_browser.setOpenExternalLinks(False)
        diff_browser.setHtml(diff_html)
        diff_browser.setMinimumHeight(300)
        layout.addWidget(diff_browser, stretch=1)

        # Action buttons underneath
        actions_layout = QHBoxLayout()

        # Left: keep existing
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

        # Middle: create separate
        middle_frame = QFrame()
        middle_frame.setFrameStyle(QFrame.StyledPanel | QFrame.Plain)
        middle_layout = QVBoxLayout(middle_frame)
        middle_layout.addWidget(QLabel("Keep both:"))
        separate_btn = QPushButton("Create separate entry")
        separate_btn.clicked.connect(lambda: self._accept_result("separate", None))
        middle_layout.addWidget(separate_btn)
        actions_layout.addWidget(middle_frame)

        # Right: keep new
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
