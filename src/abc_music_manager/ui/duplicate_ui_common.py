"""Shared duplicate UI helpers: paths for display and side-by-side diff HTML."""

from __future__ import annotations

import difflib
from pathlib import Path

from ..services.preferences import to_music_relative


def path_for_display(path: str) -> str:
    """Return path relative to Music directory for display, or full path if outside Music."""
    if not path or path.startswith("("):
        return path
    rel = to_music_relative(path)
    return rel if rel else path


def read_file_content(path: str) -> str:
    """Read file content, or return error message."""
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return f"# Error reading file: {e}"


def html_escape(s: str) -> str:
    """Escape HTML special characters."""
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def make_split_diff_html(left_path: str, right_path: str) -> str:
    """
    Generate HTML for side-by-side diff with equal 50/50 columns.
    Left: existing file (red for removed). Right: new file (green for added).
    """
    if left_path.startswith("(") or not Path(left_path).is_file():
        left_lines = [f"# File not found: {left_path}"]
    else:
        left_lines = read_file_content(left_path).splitlines()
    if right_path.startswith("(") or not Path(right_path).is_file():
        right_lines = [f"# File not found: {right_path}"]
    else:
        right_lines = read_file_content(right_path).splitlines()
    if not left_lines:
        left_lines = [""]
    if not right_lines:
        right_lines = [""]

    matcher = difflib.SequenceMatcher(None, left_lines, right_lines)
    rows: list[tuple[str, str, str, str]] = []
    left_ln = 1
    right_ln = 1

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for i, j in zip(range(i1, i2), range(j1, j2)):
                rows.append((
                    f"{left_ln} {html_escape(left_lines[i])}",
                    f"{right_ln} {html_escape(right_lines[j])}",
                    "",
                    "",
                ))
                left_ln += 1
                right_ln += 1
        elif tag == "replace":
            left_chunk = list(range(i1, i2))
            right_chunk = list(range(j1, j2))
            for k in range(max(len(left_chunk), len(right_chunk))):
                left_text = f"{left_ln} {html_escape(left_lines[left_chunk[k]])}" if k < len(left_chunk) else ""
                right_text = f"{right_ln} {html_escape(right_lines[right_chunk[k]])}" if k < len(right_chunk) else ""
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
                    f"{left_ln} {html_escape(left_lines[i])}",
                    "",
                    "removed",
                    "",
                ))
                left_ln += 1
        elif tag == "insert":
            for j in range(j1, j2):
                rows.append((
                    "",
                    f"{right_ln} {html_escape(right_lines[j])}",
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
