"""
Settings view: FolderRule list, Add/Edit/Delete, Scan library.
"""

from __future__ import annotations

import sqlite3
from typing import Callable

import flet as ft

from ..theme import SPACING_TIGHT, SPACING_DEFAULT, SPACING_SECTION, PADDING_TIGHT, COLOR_PRIMARY_CONTAINER
from ..db.folder_rule import (
    FolderRuleRow,
    RuleType,
    list_folder_rules,
    add_folder_rule,
    update_folder_rule,
    delete_folder_rule,
    get_enabled_roots,
)
from ..scanner import run_scan


def _build_rule_rows(
    conn: sqlite3.Connection,
    page: ft.Page,
    refresh_rules_list: Callable[[], None],
    on_enabled_change: Callable[[int, bool], None],
    on_delete: Callable[[int], None],
) -> list[ft.Control]:
    """Build the list of folder rule row controls."""
    rules = list_folder_rules(conn)
    rows = []
    for r in rules:
        type_label = {"library_root": "Library root", "set_root": "Set/export", "exclude": "Exclude"}[r.rule_type]
        rows.append(
            ft.Row(
                [
                    ft.Container(
                        content=ft.Text(type_label, size=12),
                        bgcolor=COLOR_PRIMARY_CONTAINER,
                        padding=ft.padding.symmetric(horizontal=PADDING_TIGHT, vertical=2),
                        border_radius=4,
                    ),
                    ft.Text(r.path, size=12, overflow=ft.TextOverflow.ELLIPSIS, expand=True),
                    ft.Switch(
                        value=r.enabled,
                        on_change=lambda e, rid=r.id: on_enabled_change(rid, e.control.value),
                    ),
                    ft.IconButton(
                        icon=ft.Icons.DELETE_OUTLINED,
                        on_click=lambda e, rid=r.id: on_delete(rid),
                    ),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            )
        )
    return rows


def build_settings_view(
    conn: sqlite3.Connection,
    page: ft.Page,
    on_scan_done: Callable[[], None],
) -> ft.Control:
    """Build Settings tab content: folder rules and Scan button."""

    rules_list_ref = ft.Ref[ft.Column]()
    progress_ref = ft.Ref[ft.ProgressBar]()
    progress_text_ref = ft.Ref[ft.Text]()

    def _on_enabled_change(rule_id: int, enabled: bool) -> None:
        update_folder_rule(conn, rule_id, enabled=enabled)
        refresh_rules_list()

    def _on_delete(rule_id: int) -> None:
        delete_folder_rule(conn, rule_id)
        refresh_rules_list()
        page.snack_bar = ft.SnackBar(content=ft.Text("Folder rule removed"))
        page.snack_bar.open = True
        page.update()

    def refresh_rules_list() -> None:
        rows = _build_rule_rows(conn, page, refresh_rules_list, _on_enabled_change, _on_delete)
        if rules_list_ref.current:
            rules_list_ref.current.controls = rows
            rules_list_ref.current.update()
        page.update()

    # FilePicker for "Browse" in Add folder rule dialog (desktop only; not in web)
    if not getattr(page, "_abc_file_picker", None):
        page._abc_file_picker = ft.FilePicker()
        page.services.append(page._abc_file_picker)
        page.update()

    def open_add_dialog(_e: ft.ControlEvent) -> None:
        rule_type_ref = ft.Ref[ft.Dropdown]()
        path_ref = ft.Ref[ft.TextField]()

        async def browse_folder(_e2: ft.ControlEvent) -> None:
            file_picker = getattr(page, "_abc_file_picker", None)
            if not file_picker:
                return
            path = await file_picker.get_directory_path(dialog_title="Select folder")
            if path is not None and path_ref.current:
                path_ref.current.value = path
                path_ref.current.update()
                page.update()

        def add_and_close(_e2: ft.ControlEvent) -> None:
            rt = rule_type_ref.current.value
            path = (path_ref.current.value or "").strip()
            if not path or not rt:
                return
            add_folder_rule(conn, rt, path)
            dialog.open = False
            page.update()
            refresh_rules_list()
            page.snack_bar = ft.SnackBar(content=ft.Text("Folder rule added"))
            page.snack_bar.open = True
            page.update()

        path_field = ft.TextField(
            ref=path_ref,
            label="Path",
            hint_text="Choose a folder or type path",
            expand=True,
        )
        browse_btn = ft.ElevatedButton(
            "Browse…",
            icon=ft.Icons.FOLDER_OPEN,
            on_click=browse_folder,
            disabled=page.web,  # Directory picker not supported in web
        )
        if page.web:
            browse_btn.tooltip = "Not available in browser; type the path."

        dialog = ft.AlertDialog(
            title=ft.Text("Add folder rule"),
            content=ft.Column(
                [
                    ft.Dropdown(
                        ref=rule_type_ref,
                        label="Type",
                        value="library_root",
                        options=[
                            ft.dropdown.Option("library_root", "Library root"),
                            ft.dropdown.Option("set_root", "Set/export folder"),
                            ft.dropdown.Option("exclude", "Exclude"),
                        ],
                    ),
                    ft.Row(
                        [path_field, browse_btn],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        spacing=8,
                    ),
                ],
                tight=True,
            ),
            actions=[
                ft.TextButton("Cancel", on_click=lambda e: _close_dialog(dialog)),
                ft.ElevatedButton("Add", on_click=add_and_close),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )

        def _close_dialog(d: ft.AlertDialog) -> None:
            d.open = False
            page.update()

        page.overlay.append(dialog)
        dialog.open = True
        page.update()

    def do_scan(_e: ft.ControlEvent) -> None:
        # Always run scan: with no roots it clears the index; with roots it indexes .abc files
        def progress(current: int, total: int) -> None:
            if progress_ref.current and progress_text_ref.current:
                progress_ref.current.value = current / total if total else 0
                progress_text_ref.current.value = f"Scanning {current} / {total}"
                page.update()

        if progress_ref.current:
            progress_ref.current.visible = True
            progress_ref.current.value = 0
        if progress_text_ref.current:
            progress_text_ref.current.visible = True
            progress_text_ref.current.value = "Starting scan..."
        page.update()

        found, scanned, errors = run_scan(conn, progress_callback=progress)
        lib_roots, set_roots, _ = get_enabled_roots(conn)
        has_roots = bool(lib_roots or set_roots)

        if progress_ref.current:
            progress_ref.current.visible = False
        if progress_text_ref.current:
            progress_text_ref.current.visible = False
        page.update()
        if found == 0 and scanned == 0:
            msg = "Library cleared." if not has_roots else "No .abc files found."
        else:
            msg = f"Found {found} .abc files, indexed {scanned}."
            if errors:
                msg += f" ({errors} failed to parse.)"
        page.snack_bar = ft.SnackBar(content=ft.Text(msg))
        page.snack_bar.open = True
        page.update()
        on_scan_done()

    content = ft.Column(
        [
            ft.Text("Settings", size=24, weight=ft.FontWeight.BOLD),
            ft.Divider(),
            ft.Text("Folder rules", size=16, weight=ft.FontWeight.W_500),
            ft.Text("Add library roots to index .abc files. Set/export folders are indexed but hidden from the main library by default.", size=12),
            ft.Row(
                [
                    ft.ElevatedButton("Add folder rule", icon=ft.Icons.ADD, on_click=open_add_dialog),
                    ft.ElevatedButton("Scan library", icon=ft.Icons.REFRESH, on_click=do_scan),
                ],
                spacing=SPACING_DEFAULT,
            ),
            ft.Container(ref=progress_ref, content=ft.ProgressBar(visible=False), height=4),
            ft.Container(ref=progress_text_ref, content=ft.Text(visible=False), height=20),
            ft.Divider(),
            ft.Container(
                content=ft.Column(
                    ref=rules_list_ref,
                    controls=_build_rule_rows(conn, page, refresh_rules_list, _on_enabled_change, _on_delete),
                    spacing=SPACING_TIGHT,
                ),
                expand=True,
            ),
        ],
        expand=True,
        scroll=ft.ScrollMode.AUTO,
        spacing=SPACING_SECTION,
    )

    return ft.Container(content=content, expand=True)
