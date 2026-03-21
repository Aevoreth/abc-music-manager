"""
ABC parse exceptions.
"""

from __future__ import annotations


class AbcParseError(Exception):
    """Error parsing ABC content."""

    def __init__(self, message: str, filename: str | None = None, line: int = 0, column: int = 0) -> None:
        super().__init__(message)
        self.message = message
        self.filename = filename
        self.line = line
        self.column = column

    def __str__(self) -> str:
        parts = [self.message]
        if self.filename:
            parts.append(f" in {self.filename}")
        if self.line > 0:
            parts.append(f" line {self.line}")
        if self.column > 0:
            parts.append(f" column {self.column}")
        return "".join(parts)


class LotroParseError(AbcParseError):
    """LOTRO-specific parse error (e.g. note too high/low)."""
