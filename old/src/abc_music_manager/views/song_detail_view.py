"""
Song Detail view (minimal): metadata and part list. REQUIREMENTS §1 Song Detail/Edit.
"""

from __future__ import annotations

import sqlite3
from typing import Callable

import flet as ft

from ..db.library_query import get_song_for_detail
from ..theme import SPACING_TIGHT, SPACING_SECTION


def _format_duration(seconds) -> str:
    if seconds is None:
        return "—"
    m, s = divmod(seconds, 60)
    return f"{m}:{s:02d}"


def build_song_detail_view(
    conn: sqlite3.Connection,
    song_id: int,
    on_back: Callable[[], None],
) -> ft.Control:
    """Build Song Detail panel: metadata, part list, Back button."""

    song = get_song_for_detail(conn, song_id)
    if not song:
        return ft.Container(
            content=ft.Column(
                [ft.Text("Song not found."), ft.TextButton("Back", on_click=lambda e: on_back())],
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            expand=True,
            alignment=ft.Alignment.CENTER,
        )

    meta = ft.Column(
        [
            ft.Row([ft.Text("Title", weight=ft.FontWeight.W_500, width=120), ft.Text(song["title"] or "—")]),
            ft.Row([ft.Text("Composer(s)", weight=ft.FontWeight.W_500, width=120), ft.Text(song["composers"] or "—")]),
            ft.Row([ft.Text("Transcriber", weight=ft.FontWeight.W_500, width=120), ft.Text(song["transcriber"] or "—")]),
            ft.Row([ft.Text("Duration", weight=ft.FontWeight.W_500, width=120), ft.Text(_format_duration(song["duration_seconds"]))]),
            ft.Row([ft.Text("Part count", weight=ft.FontWeight.W_500, width=120), ft.Text(str(song["part_count"]))]),
            ft.Row([ft.Text("Export timestamp", weight=ft.FontWeight.W_500, width=120), ft.Text(song.get("export_timestamp") or "—")]),
            ft.Row([ft.Text("Status", weight=ft.FontWeight.W_500, width=120), ft.Text(song.get("status_name") or "—")]),
            ft.Row([ft.Text("Rating", weight=ft.FontWeight.W_500, width=120), ft.Text(str(song["rating"]) if song.get("rating") is not None else "—")]),
        ],
        spacing=SPACING_TIGHT,
    )

    part_rows = [
        ft.DataRow(
            cells=[
                ft.DataCell(ft.Text(str(p.get("part_number", "—")))),
                ft.DataCell(ft.Text(p.get("part_name") or "—")),
                ft.DataCell(ft.Text(p.get("instrument_name") or "—")),
            ]
        )
        for p in song.get("parts") or []
    ]
    parts_table = ft.DataTable(
        columns=[
            ft.DataColumn(ft.Text("Part #")),
            ft.DataColumn(ft.Text("Part name")),
            ft.DataColumn(ft.Text("Made for instrument")),
        ],
        rows=part_rows,
    )

    content = ft.Column(
        [
            ft.Row(
                [ft.IconButton(icon=ft.Icons.ARROW_BACK, on_click=lambda e: on_back()), ft.Text("Song detail", size=20, weight=ft.FontWeight.BOLD)],
                alignment=ft.MainAxisAlignment.START,
            ),
            ft.Divider(),
            ft.Text("Metadata", size=14, weight=ft.FontWeight.W_500),
            meta,
            ft.Divider(),
            ft.Text("Parts", size=14, weight=ft.FontWeight.W_500),
            ft.Container(content=parts_table),
        ],
        expand=True,
        scroll=ft.ScrollMode.AUTO,
        spacing=SPACING_SECTION,
    )
    return ft.Container(content=content, expand=True)
