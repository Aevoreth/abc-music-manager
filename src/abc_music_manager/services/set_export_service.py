"""
Set export: copy ABC files to folder and/or zip, optionally with CSV part sheet.
"""

from __future__ import annotations

import csv
import json
import re
import shutil
import sqlite3
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from ..db.band_repo import list_layout_slots_for_export, set_export_column_order
from ..db.library_query import get_primary_file_path_for_song
from ..db.player_repo import list_players
from ..db.setlist_repo import (
    get_setlist_band_assignments,
    list_setlist_items_with_song_meta,
)
from ..db.setlist_repo import SetlistItemSongMetaRow
from ..db.instrument import get_instrument_name
from .abcp_service import write_abcp
from .abc_part_title_rewrite import rewrite_abc_part_t_lines
from .filename_template import (
    compute_part_numeration,
    format_filename,
    format_part_name,
)


# Invalid path chars for Windows (and common across OS)
_INVALID_PATH_CHARS = re.compile(r'[<>:"/\\|?*]')


def _sanitize_for_path(s: str) -> str:
    """Remove or replace invalid path characters."""
    return _INVALID_PATH_CHARS.sub("", s).strip() or "untitled"


@dataclass
class SetExportSettings:
    output_directory: Path
    set_name: str
    export_as_folder: bool
    export_as_zip: bool
    rename_abc_files: bool
    filename_pattern: str
    whitespace_replace: str
    part_count_zero_padded: bool
    export_csv_part_sheet: bool
    export_abcp_playlist: bool
    include_composer_in_csv: bool
    csv_use_visible_columns: bool
    csv_columns_enabled: dict[str, bool]
    csv_part_columns: str  # "part" or "instrument"
    rename_parts: bool
    part_name_pattern: str
    csv_part_rename_rules: list[tuple[str, str]]


def normalize_csv_part_rename_rules(raw: Any) -> list[tuple[str, str]]:
    """Load find/replace pairs from preferences JSON. Skips rules with empty find text."""
    out: list[tuple[str, str]] = []
    if not isinstance(raw, list):
        return out
    for item in raw:
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            find_s, repl_s = str(item[0]), str(item[1])
        elif isinstance(item, dict):
            f = item.get("find")
            r = item.get("replace")
            if f is None:
                continue
            find_s, repl_s = str(f), "" if r is None else str(r)
        else:
            continue
        if not find_s.strip():
            continue
        out.append((find_s, repl_s))
    return out


def apply_csv_part_display_renames(text: str, rules: list[tuple[str, str]]) -> str:
    """Apply find/replace rules in order (literal substring replace)."""
    s = text
    for find_s, repl_s in rules:
        if not find_s:
            continue
        s = s.replace(find_s, repl_s)
    return s


def _csv_part_cell_label(
    conn: sqlite3.Connection,
    part_entry: dict,
    part_number: int,
    use_instrument: bool,
    settings: SetExportSettings,
) -> str:
    """Text shown after 'n: ' in band-layout CSV part cells; same rules as part vs instrument + CSV renames."""
    pname = (part_entry.get("part_name") or "").strip() or f"Part {part_number}"
    if use_instrument and part_entry.get("instrument_id"):
        iname = get_instrument_name(conn, part_entry["instrument_id"])
        pname = iname or pname
    return apply_csv_part_display_renames(pname, settings.csv_part_rename_rules)


def _csv_appendix_made_for_catalog_name(conn: sqlite3.Connection, part_entry: dict) -> str:
    """
    Instrument catalog name for the part's %%made-for (stored as instrument_id when the song was parsed).
    Does not use %%part-name and does not apply CSV Part Renaming rules.
    """
    iid = part_entry.get("instrument_id")
    if iid is None:
        return ""
    try:
        iid_int = int(iid)
    except (TypeError, ValueError):
        return ""
    return get_instrument_name(conn, iid_int) or ""


# CSV columns for custom mode
CSV_AVAILABLE_COLUMNS = [
    "Title",
    "Composers",
    "Transcriber",
    "Duration",
    "Part Count",
    "File Name",
    "Notes",
    "Status",
]
CSV_DEFAULT_ENABLED = {"Title", "Part Count", "Duration", "Composers", "Transcriber"}


def _format_duration(seconds: int | None) -> str:
    if seconds is None:
        return ""
    m = seconds // 60
    s = seconds % 60
    return f"{m}:{s:02d}"


def _get_metadata_columns(settings: SetExportSettings) -> list[str]:
    """Return ordered list of metadata column names for CSV."""
    if settings.csv_use_visible_columns:
        cols = ["Title", "Parts", "Duration", "Artist"]
        if settings.include_composer_in_csv:
            cols.insert(2, "Composers")  # Title, Parts, Composers, Duration, Artist
        return cols
    return [c for c in CSV_AVAILABLE_COLUMNS if settings.csv_columns_enabled.get(c, False)]


def _get_metadata_value(
    col: str,
    row: SetlistItemSongMetaRow,
    file_path: str | None,
) -> str:
    """Get value for a metadata column from SetlistItemSongMetaRow."""
    if col == "Title":
        return row.title or ""
    if col == "Composers" or col == "Artist":
        return row.composers or ""
    if col == "Transcriber":
        return row.transcriber or ""
    if col == "Duration" or col == "Parts":
        if col == "Duration":
            return _format_duration(row.duration_seconds)
        return str(row.part_count)
    if col == "Part Count":
        return str(row.part_count)
    if col == "File Name":
        return Path(file_path).stem if file_path else ""
    if col == "Notes":
        return row.notes or ""
    if col == "Status":
        return row.status_name or ""
    return ""


def _get_part_display(
    parts_json: str | None,
    part_number: int,
    use_instrument: bool,
    conn: sqlite3.Connection,
) -> str:
    """Get part name or instrument name for a part."""
    if not parts_json:
        return f"Part {part_number}"
    try:
        parts = json.loads(parts_json)
    except (json.JSONDecodeError, TypeError):
        return f"Part {part_number}"
    for p in parts:
        if int(p.get("part_number") or 0) == part_number:
            if use_instrument:
                iid = p.get("instrument_id")
                if iid:
                    name = get_instrument_name(conn, iid)
                    if name:
                        return name
            return (p.get("part_name") or "").strip() or f"Part {part_number}"
    return f"Part {part_number}"


def _player_name_for_part(
    assigns: dict[int, int | None],
    players_by_id: dict[int, str],
    part_number: int,
) -> str:
    """Band layout player display name for this part; lowest player_id if multiple."""
    candidates = sorted(pid for pid, pn in assigns.items() if pn == part_number)
    if not candidates:
        return ""
    pid = candidates[0]
    return players_by_id.get(pid) or f"Player {pid}"


def _build_part_t_line_map(
    conn: sqlite3.Connection,
    row: SetlistItemSongMetaRow,
    file_path: str,
    list_index: int,
    band_layout_id: int | None,
    assigns: dict[int, int | None],
    players_by_id: dict[int, str],
    settings: SetExportSettings,
) -> dict[int, str]:
    """part_number -> new T: body text for rewrite_abc_part_t_lines."""
    try:
        parts = json.loads(row.parts_json) if row.parts_json else []
    except (json.JSONDecodeError, TypeError):
        parts = []
    if not parts:
        return {}

    numer = compute_part_numeration(parts)
    out: dict[int, str] = {}
    for p in parts:
        pn = int(p.get("part_number") or 0)
        if not pn:
            continue
        raw_name = p.get("part_name")
        part_name_str = "" if raw_name is None else str(raw_name)
        tf = p.get("title_from_t")
        title_from_t = "" if tf is None else str(tf)
        iid = p.get("instrument_id")
        inst = ""
        if iid:
            inst = get_instrument_name(conn, iid) or ""
        player = _player_name_for_part(assigns, players_by_id, pn) if band_layout_id else ""

        new_title = format_part_name(
            settings.part_name_pattern,
            file_path=file_path,
            index=list_index,
            title=row.title or "",
            composers=row.composers or "",
            transcriber=row.transcriber,
            duration_seconds=row.duration_seconds,
            part_count=row.part_count,
            part_instrument=inst,
            part_name=part_name_str,
            part_title=title_from_t,
            part_number_display=str(pn),
            player_assignment=player,
            numeration=numer.get(pn, ""),
            whitespace_replace=settings.whitespace_replace,
            part_count_zero_padded=settings.part_count_zero_padded,
        )
        out[pn] = new_title
    return out


def _generate_csv(
    conn: sqlite3.Connection,
    items: list[SetlistItemSongMetaRow],
    file_paths: dict[int, str],
    settings: SetExportSettings,
    band_layout_id: int | None,
    output_path: Path,
    player_ids_in_order: list[int] | None = None,
) -> None:
    """Generate CSV part sheet at output_path. When band_layout_id is set, use player_ids_in_order
    for column order if provided, else list_layout_slots_for_export."""
    metadata_cols = _get_metadata_columns(settings)
    use_instrument = settings.csv_part_columns == "instrument"
    player_ids: list[int] = []
    player_names: list[str] = []

    if band_layout_id:
        if player_ids_in_order is not None:
            player_ids = player_ids_in_order
        else:
            slots = list_layout_slots_for_export(conn, band_layout_id)
            player_ids = [s.player_id for s in slots]
        players = {p.id: p for p in list_players(conn) if p.id in player_ids}
        player_names = [(players[pid].name if pid in players else f"Player {pid}") for pid in player_ids]
        headers = metadata_cols + player_names
    else:
        max_parts = max((r.part_count for r in items), default=0)
        headers = metadata_cols + [f"Part {i + 1}" for i in range(max_parts)]

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)

        for row in items:
            fp = file_paths.get(row.item.song_id)
            meta_vals = [_get_metadata_value(c, row, fp) for c in metadata_cols]

            if band_layout_id:
                assignments = get_setlist_band_assignments(conn, row.item.id)
                parts = json.loads(row.parts_json) if row.parts_json else []
                parts_by_num = {int(p.get("part_number") or 0): p for p in parts}
                for pid in player_ids:
                    pn = assignments.get(pid)
                    if pn is not None and pn in parts_by_num:
                        p = parts_by_num[pn]
                        pname = _csv_part_cell_label(conn, p, pn, use_instrument, settings)
                        meta_vals.append(f"{pn}: {pname}")
                    else:
                        meta_vals.append("")
            else:
                parts = json.loads(row.parts_json) if row.parts_json else []
                for i in range(max_parts):
                    pnum = i + 1
                    cell = _get_part_display(row.parts_json, pnum, use_instrument, conn)
                    meta_vals.append(
                        apply_csv_part_display_renames(cell, settings.csv_part_rename_rules)
                    )

            writer.writerow(meta_vals)

        if band_layout_id and player_ids:
            for _ in range(3):
                writer.writerow([""] * len(headers))
            writer.writerow(["Player Name", "Instruments needed"])
            by_player: dict[int, set[str]] = {pid: set() for pid in player_ids}
            for row in items:
                assignments = get_setlist_band_assignments(conn, row.item.id)
                try:
                    parts = json.loads(row.parts_json) if row.parts_json else []
                except (json.JSONDecodeError, TypeError):
                    parts = []
                parts_by_num = {int(p.get("part_number") or 0): p for p in parts}
                for pid in player_ids:
                    pn = assignments.get(pid)
                    if pn is not None and pn in parts_by_num:
                        label = _csv_appendix_made_for_catalog_name(conn, parts_by_num[pn])
                        if label:
                            by_player[pid].add(label)
            for pid, display_name in zip(player_ids, player_names):
                ordered = sorted(by_player[pid], key=str.casefold)
                writer.writerow([display_name, ", ".join(ordered)])


def export_set(
    conn: sqlite3.Connection,
    setlist_id: int,
    setlist_name: str,
    band_layout_id: int | None,
    settings: SetExportSettings,
    player_ids_in_order: list[int] | None,
    status_callback: Callable[[str], None] | None = None,
) -> None:
    """
    Export setlist to folder and/or zip.
    Raises ValueError on error (e.g. output exists, no songs).
    """
    def status(msg: str) -> None:
        if status_callback:
            status_callback(msg)

    set_name = _sanitize_for_path(settings.set_name or setlist_name or "Untitled Set")
    out_dir = Path(settings.output_directory)
    out_dir.mkdir(parents=True, exist_ok=True)

    items = list_setlist_items_with_song_meta(conn, setlist_id)
    if not items:
        raise ValueError("Setlist has no songs to export.")

    # Collect file paths
    file_paths: dict[int, str] = {}
    for row in items:
        fp = get_primary_file_path_for_song(conn, row.item.song_id)
        if fp:
            file_paths[row.item.song_id] = fp

    # Save player column order if provided
    if band_layout_id and player_ids_in_order is not None:
        set_export_column_order(conn, band_layout_id, player_ids_in_order)

    folder_path = out_dir / set_name
    zip_path = out_dir / f"{set_name}.zip"

    if settings.export_as_folder and folder_path.exists():
        raise ValueError(f"Output folder already exists: {folder_path}")
    if settings.export_as_zip and zip_path.exists():
        raise ValueError(f"Output zip file already exists: {zip_path}")

    # Create staging folder (for zip-only we use temp; for folder we use the real path)
    if settings.export_as_folder:
        folder_path.mkdir(parents=True)
        status("Created output folder...")
        copy_to = folder_path
    else:
        copy_to = Path(tempfile.mkdtemp(prefix="set_export_"))
        status("Preparing export...")

    try:
        players_by_id = {p.id: p.name for p in list_players(conn)}

        # Build target filenames
        used_names: dict[str, int] = {}
        export_entries: list[tuple[int, SetlistItemSongMetaRow, Path, str]] = []

        for i, row in enumerate(items):
            if row.item.song_id not in file_paths:
                continue
            src = Path(file_paths[row.item.song_id])
            fp = file_paths[row.item.song_id]
            if settings.rename_abc_files:
                base = format_filename(
                    settings.filename_pattern,
                    file_path=fp,
                    index=i,
                    title=row.title,
                    composers=row.composers,
                    transcriber=row.transcriber,
                    duration_seconds=row.duration_seconds,
                    part_count=row.part_count,
                    whitespace_replace=settings.whitespace_replace,
                    part_count_zero_padded=settings.part_count_zero_padded,
                )
            else:
                base = src.name
            # Deduplicate
            if base in used_names:
                used_names[base] += 1
                stem = Path(base).stem
                ext = Path(base).suffix
                base = f"{stem}_{used_names[base]}{ext}"
            else:
                used_names[base] = 1
            export_entries.append((i, row, src, base))

        for j, (list_i, row, src, base) in enumerate(export_entries):
            dest = copy_to / base
            if settings.rename_parts:
                assigns = get_setlist_band_assignments(conn, row.item.id) if band_layout_id else {}
                part_map = _build_part_t_line_map(
                    conn,
                    row,
                    file_path=file_paths[row.item.song_id],
                    list_index=list_i,
                    band_layout_id=band_layout_id,
                    assigns=assigns,
                    players_by_id=players_by_id,
                    settings=settings,
                )
                text = src.read_text(encoding="utf-8", errors="replace")
                new_text = rewrite_abc_part_t_lines(text, part_map)
                dest.write_text(new_text, encoding="utf-8")
            else:
                dest.write_bytes(src.read_bytes())
            status(f"Copied ABC {j + 1} of {len(export_entries)}...")

        if settings.export_csv_part_sheet:
            status("Generating CSV part sheet...")
            _generate_csv(
                conn,
                items,
                file_paths,
                settings,
                band_layout_id,
                copy_to / f"{set_name}.csv",
                player_ids_in_order=player_ids_in_order,
            )

        if settings.export_abcp_playlist and export_entries:
            status("Writing ABCP playlist...")
            rel_paths = [Path(base).as_posix() for _, _, _, base in export_entries]
            write_abcp(copy_to / f"{set_name}.abcp", rel_paths)

        if settings.export_as_zip:
            if not settings.export_as_folder:
                # Zip from temp dir
                status("Creating zip file...")
                with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                    for p in copy_to.rglob("*"):
                        if p.is_file():
                            arcname = p.relative_to(copy_to)
                            zf.write(p, arcname)
            else:
                # Zip the folder we created
                status("Creating zip file...")
                with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                    for p in folder_path.rglob("*"):
                        if p.is_file():
                            arcname = p.relative_to(folder_path)
                            zf.write(p, arcname)

        if not settings.export_as_folder:
            shutil.rmtree(copy_to, ignore_errors=True)

        status("Export finished.")
    except Exception:
        if not settings.export_as_folder and copy_to.exists():
            shutil.rmtree(copy_to, ignore_errors=True)
        raise
