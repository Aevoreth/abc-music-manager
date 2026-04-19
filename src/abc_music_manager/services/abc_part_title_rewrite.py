"""
Rewrite per-part T: lines inside X: blocks for set export. Mirrors part boundaries from parsing.abc_parser._parse_parts.
"""

from __future__ import annotations

import re

_X_LINE = re.compile(r"^X:\s*(\d+)", re.IGNORECASE)


def _line_ending(line: str) -> str:
    if line.endswith("\r\n"):
        return "\r\n"
    if line.endswith("\r"):
        return "\r"
    return "\n"


def sanitize_t_title_value(s: str) -> str:
    """Single-line value for T: — no newlines."""
    return " ".join(s.replace("\r", " ").replace("\n", " ").split()).strip()


def rewrite_abc_part_t_lines(content: str, part_num_to_title: dict[int, str]) -> str:
    """
    For each X: block, if part_num_to_title contains that X: number, set the first T: line
    in the block to the new value, or insert T: after the X: line if none exists.
    Other lines (including %%part-name) are unchanged.
    """
    if not part_num_to_title:
        return content

    lines = content.splitlines(keepends=True)
    out: list[str] = []
    i = 0
    n = len(lines)

    while i < n:
        raw = lines[i]
        sl = raw.rstrip("\r\n").strip()
        m = _X_LINE.match(sl)
        if not m:
            out.append(raw)
            i += 1
            continue

        part_num = int(m.group(1))
        out.append(raw)
        i += 1

        block_start = i
        first_t_idx: int | None = None
        while i < n:
            sl2 = lines[i].rstrip("\r\n").strip()
            if _X_LINE.match(sl2):
                break
            if first_t_idx is None and len(sl2) >= 2 and sl2.upper().startswith("T:"):
                first_t_idx = i
            i += 1

        new_title = part_num_to_title.get(part_num)
        if new_title is None:
            out.extend(lines[block_start:i])
            continue

        safe = sanitize_t_title_value(new_title)
        t_body = f"T: {safe}" if safe else "T:"

        if first_t_idx is not None:
            for j in range(block_start, i):
                if j == first_t_idx:
                    out.append(t_body + _line_ending(lines[j]))
                else:
                    out.append(lines[j])
        else:
            ending = _line_ending(lines[block_start]) if block_start < i else "\n"
            out.append(t_body + ending)
            out.extend(lines[block_start:i])

    return "".join(out)
