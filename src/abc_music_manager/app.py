"""
Main Flet application: window, dark theme, navigation (Library, Settings, Song Detail).
"""

import sqlite3
import flet as ft

from .db import get_db_path
from .theme import apply_theme, COLOR_BACKGROUND
from .views import build_settings_view, build_library_view, build_song_detail_view


def main(page: ft.Page) -> None:
    page.title = "ABC Music Manager"
    page.window.min_width = 900
    page.window.min_height = 600
    apply_theme(page)

    conn = sqlite3.connect(str(get_db_path()))
    content_area = ft.Ref[ft.Container]()
    rail_ref = ft.Ref[ft.NavigationRail]()

    def show_library() -> None:
        content_area.current.content = build_library_view(conn, page, on_open_song=show_song_detail)
        content_area.current.update()
        if rail_ref.current:
            rail_ref.current.selected_index = 0
            rail_ref.current.update()
        page.update()

    def show_settings() -> None:
        content_area.current.content = build_settings_view(conn, page, on_scan_done=show_library)
        content_area.current.update()
        if rail_ref.current:
            rail_ref.current.selected_index = 1
            rail_ref.current.update()
        page.update()

    def show_song_detail(song_id: int) -> None:
        content_area.current.content = build_song_detail_view(conn, song_id, on_back=show_library)
        content_area.current.update()
        if rail_ref.current:
            rail_ref.current.selected_index = 0
            rail_ref.current.update()
        page.update()

    def on_nav_change(e: ft.ControlEvent) -> None:
        if e.control.selected_index == 1:
            show_settings()
        else:
            show_library()

    content = ft.Container(
        ref=content_area,
        content=build_library_view(conn, page, on_open_song=show_song_detail),
        expand=True,
        bgcolor=COLOR_BACKGROUND,
    )

    rail = ft.NavigationRail(
        ref=rail_ref,
        selected_index=0,
        label_type=ft.NavigationRailLabelType.ALL,
        min_width=100,
        min_extended_width=180,
        destinations=[
            ft.NavigationRailDestination(icon=ft.Icons.MUSIC_NOTE, label="Library", selected_icon=ft.Icons.MUSIC_NOTE),
            ft.NavigationRailDestination(icon=ft.Icons.SETTINGS, label="Settings", selected_icon=ft.Icons.SETTINGS),
        ],
        on_change=on_nav_change,
    )

    page.add(
        ft.Container(
            content=ft.Row(
                [
                    rail,
                    ft.VerticalDivider(width=1),
                    content,
                ],
                expand=True,
            ),
            expand=True,
            bgcolor=COLOR_BACKGROUND,
        ),
    )


def run_app() -> None:
    ft.app(target=main)
