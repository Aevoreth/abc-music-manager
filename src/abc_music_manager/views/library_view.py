"""
Library view: table of songs with filters. REQUIREMENTS §1.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Callable, Optional

import flet as ft

from ..db.library_query import LibrarySongRow, list_library_songs, get_status_list
from ..theme import SPACING_DEFAULT, SPACING_SECTION, PADDING_TIGHT, COLOR_SURFACE_VARIANT


def _format_duration(seconds: Optional[int]) -> str:
    if seconds is None:
        return "—"
    m, s = divmod(seconds, 60)
    return f"{m}:{s:02d}"


def _format_last_played(iso_str: Optional[str]) -> str:
    if not iso_str:
        return "—"
    try:
        # Assume ISO format
        if "T" in iso_str:
            dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        else:
            dt = datetime.fromisoformat(iso_str)
        now = datetime.now(timezone.utc)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        delta = now - dt
        if delta.days > 365:
            return f"{delta.days // 365}y ago"
        if delta.days > 30:
            return f"{delta.days // 30} mo ago"
        if delta.days > 0:
            return f"{delta.days}d ago"
        if delta.seconds >= 3600:
            return f"{delta.seconds // 3600}h ago"
        if delta.seconds >= 60:
            return f"{delta.seconds // 60}m ago"
        return "Just now"
    except Exception:
        return "—"


def build_library_view(
    conn: sqlite3.Connection,
    page: ft.Page,
    on_open_song: Callable[[int], None],
) -> ft.Control:
    """Build Library tab: filters and song table. Selecting a row calls on_open_song(song_id)."""

    table_ref = ft.Ref[ft.DataTable]()
    title_filter_ref = ft.Ref[ft.TextField]()
    status_dropdown_ref = ft.Ref[ft.Dropdown]()

    def run_query() -> list[LibrarySongRow]:
        title_sub = title_filter_ref.current.value.strip() if title_filter_ref.current and title_filter_ref.current.value else None
        status_ids = None
        if status_dropdown_ref.current and status_dropdown_ref.current.value:
            try:
                status_ids = [int(status_dropdown_ref.current.value)]
            except (ValueError, TypeError):
                pass
        return list_library_songs(
            conn,
            title_substring=title_sub,
            status_ids=status_ids,
        )

    def refresh_table() -> None:
        rows_data = run_query()
        if not table_ref.current:
            return
        table_ref.current.rows = [
            ft.DataRow(
                cells=[
                    ft.DataCell(ft.Text(r.title or "—", no_wrap=True, overflow=ft.TextOverflow.ELLIPSIS)),
                    ft.DataCell(ft.Text(r.composers or "—", no_wrap=True, overflow=ft.TextOverflow.ELLIPSIS)),
                    ft.DataCell(ft.Text(r.transcriber or "—", no_wrap=True, overflow=ft.TextOverflow.ELLIPSIS)),
                    ft.DataCell(ft.Text(_format_duration(r.duration_seconds))),
                    ft.DataCell(ft.Text(str(r.part_count))),
                    ft.DataCell(ft.Text(_format_last_played(r.last_played_at))),
                    ft.DataCell(ft.Text(str(r.total_plays))),
                    ft.DataCell(ft.Text(str(r.rating) if r.rating is not None else "—")),
                    ft.DataCell(
                        ft.Container(
                            content=ft.Text(r.status_name or "—", size=11),
                            bgcolor=r.status_color or COLOR_SURFACE_VARIANT,
                            padding=ft.padding.symmetric(horizontal=PADDING_TIGHT, vertical=2),
                            border_radius=4,
                        )
                        if (r.status_name or "—") != "—"
                        else ft.Text("—")
                    ),
                    ft.DataCell(ft.Icon(ft.Icons.EVENT_NOTE, size=14) if r.in_upcoming_set else ft.Text("")),
                    ft.DataCell(ft.Icon(ft.Icons.NOTE, size=14) if r.notes else ft.Text("")),
                    ft.DataCell(ft.Icon(ft.Icons.LYRICS, size=14) if r.lyrics else ft.Text("")),
                ],
                on_select_change=lambda e, sid=r.song_id: _on_row_select(e, sid),
            )
            for r in rows_data
        ]
        table_ref.current.update()
        page.update()

    def _on_row_select(e: ft.ControlEvent, song_id: int) -> None:
        if e.control.selected:
            on_open_song(song_id)

    def on_filter_change(_e: ft.ControlEvent) -> None:
        refresh_table()

    status_options = [ft.dropdown.Option("", "All statuses")]
    for sid, sname in get_status_list(conn):
        status_options.append(ft.dropdown.Option(str(sid), sname))

    filter_row = ft.Row(
        [
            ft.TextField(
                ref=title_filter_ref,
                label="Title",
                hint_text="Search…",
                width=200,
                on_submit=on_filter_change,
                on_change=on_filter_change,
            ),
            ft.Dropdown(
                ref=status_dropdown_ref,
                label="Status",
                width=150,
                options=status_options,
                on_select=on_filter_change,
            ),
            ft.ElevatedButton("Refresh", icon=ft.Icons.REFRESH, on_click=lambda e: refresh_table()),
        ],
        spacing=SPACING_DEFAULT,
        wrap=True,
    )

    # Build initial table
    rows_data = list_library_songs(conn)
    data_table = ft.DataTable(
        ref=table_ref,
        columns=[
            ft.DataColumn(ft.Text("Title")),
            ft.DataColumn(ft.Text("Composer(s)")),
            ft.DataColumn(ft.Text("Transcriber")),
            ft.DataColumn(ft.Text("Duration")),
            ft.DataColumn(ft.Text("Parts")),
            ft.DataColumn(ft.Text("Last played")),
            ft.DataColumn(ft.Text("Plays")),
            ft.DataColumn(ft.Text("Rating")),
            ft.DataColumn(ft.Text("Status")),
            ft.DataColumn(ft.Text("In set")),
            ft.DataColumn(ft.Text("Notes")),
            ft.DataColumn(ft.Text("Lyrics")),
        ],
        rows=[
            ft.DataRow(
                cells=[
                    ft.DataCell(ft.Text(row.title or "—", no_wrap=True, overflow=ft.TextOverflow.ELLIPSIS)),
                    ft.DataCell(ft.Text(row.composers or "—", no_wrap=True, overflow=ft.TextOverflow.ELLIPSIS)),
                    ft.DataCell(ft.Text(row.transcriber or "—", no_wrap=True, overflow=ft.TextOverflow.ELLIPSIS)),
                    ft.DataCell(ft.Text(_format_duration(row.duration_seconds))),
                    ft.DataCell(ft.Text(str(row.part_count))),
                    ft.DataCell(ft.Text(_format_last_played(row.last_played_at))),
                    ft.DataCell(ft.Text(str(row.total_plays))),
                    ft.DataCell(ft.Text(str(row.rating) if row.rating is not None else "—")),
                    ft.DataCell(
                        ft.Container(
                            content=ft.Text(row.status_name or "—", size=11),
                            bgcolor=row.status_color or COLOR_SURFACE_VARIANT,
                            padding=ft.padding.symmetric(horizontal=PADDING_TIGHT, vertical=2),
                            border_radius=4,
                        )
                        if (row.status_name or "—") != "—"
                        else ft.Text("—")
                    ),
                    ft.DataCell(ft.Icon(ft.Icons.EVENT_NOTE, size=14) if row.in_upcoming_set else ft.Text("")),
                    ft.DataCell(ft.Icon(ft.Icons.NOTE, size=14) if row.notes else ft.Text("")),
                    ft.DataCell(ft.Icon(ft.Icons.LYRICS, size=14) if row.lyrics else ft.Text("")),
                ],
                on_select_change=lambda e, sid=row.song_id: _on_row_select(e, sid),
            )
            for row in rows_data
        ],
    )

    content = ft.Column(
        [
            ft.Text("Library", size=24, weight=ft.FontWeight.BOLD),
            ft.Divider(),
            filter_row,
            ft.Container(
                content=data_table,
                expand=True,
            ),
        ],
        expand=True,
        scroll=ft.ScrollMode.AUTO,
        spacing=SPACING_SECTION,
    )
    return ft.Container(content=content, expand=True)
