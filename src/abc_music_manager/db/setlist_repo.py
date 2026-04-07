"""Setlist and SetlistItem CRUD. DATA_MODEL §3."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .setlist_folder_repo import SetlistFolderRow, list_folders
from .song_layout_repo import get_or_create_song_layout_for_band, delete_song_layout


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


_UNSET: Any = object()


@dataclass
class SetlistRow:
    id: int
    name: str
    band_layout_id: int | None
    folder_id: int | None
    sort_order: int
    locked: bool
    default_change_duration_seconds: int | None
    notes: str | None
    set_date: str | None
    set_time: str | None
    target_duration_seconds: int | None
    created_at: str
    updated_at: str


@dataclass
class SetlistItemRow:
    id: int
    setlist_id: int
    song_id: int
    position: int
    override_change_duration_seconds: int | None
    song_layout_id: int | None
    created_at: str
    updated_at: str


@dataclass
class SetlistItemSongMetaRow:
    """SetlistItem joined with Song fields for the setlist editor table and set export."""

    item: SetlistItemRow
    title: str
    composers: str
    duration_seconds: int | None
    part_count: int
    parts_json: str | None
    transcriber: str | None = None
    notes: str | None = None
    status_name: str | None = None


def list_setlists(conn: sqlite3.Connection) -> list[SetlistRow]:
    """Return all setlists. Order: folders by sort_order, then uncategorized; within each, by sort_order then name."""
    cur = conn.execute(
        """SELECT s.id, s.name, s.band_layout_id, s.folder_id, COALESCE(s.sort_order, 0),
                  s.locked, s.default_change_duration_seconds,
                  COALESCE(s.notes, ''), s.set_date, s.set_time, s.target_duration_seconds,
                  s.created_at, s.updated_at
           FROM Setlist s
           LEFT JOIN SetlistFolder f ON s.folder_id = f.id
           ORDER BY
             CASE WHEN s.folder_id IS NULL THEN 1 ELSE 0 END,
             COALESCE(f.sort_order, 999999),
             COALESCE(s.sort_order, 999999),
             s.name"""
    )
    return [
        SetlistRow(
            id=r[0],
            name=r[1],
            band_layout_id=r[2],
            folder_id=r[3],
            sort_order=int(r[4] or 0),
            locked=bool(r[5]),
            default_change_duration_seconds=r[6],
            notes=r[7] if r[7] else None,
            set_date=r[8] if r[8] else None,
            set_time=r[9] if r[9] else None,
            target_duration_seconds=r[10],
            created_at=r[11],
            updated_at=r[12],
        )
        for r in cur.fetchall()
    ]


def list_setlists_grouped_by_folder(
    conn: sqlite3.Connection,
) -> list[tuple[SetlistFolderRow | None, list[SetlistRow]]]:
    """Return (folder or None for Uncategorized, setlists) for each group. Folders ordered by sort_order; Uncategorized last. Empty folders are included."""
    folders = list_folders(conn)
    all_setlists = list_setlists(conn)
    result: list[tuple[SetlistFolderRow | None, list[SetlistRow]]] = []
    for folder in folders:
        group = [s for s in all_setlists if s.folder_id == folder.id]
        result.append((folder, group))
    uncategorized = [s for s in all_setlists if s.folder_id is None]
    if uncategorized:
        result.append((None, uncategorized))
    return result


def get_setlists_containing_song(conn: sqlite3.Connection, song_id: int) -> list[tuple[int, str]]:
    """Return (setlist_id, setlist_name) for every setlist that contains this song."""
    cur = conn.execute(
        """SELECT sl.id, sl.name FROM Setlist sl
           JOIN SetlistItem si ON si.setlist_id = sl.id
           WHERE si.song_id = ? ORDER BY sl.name""",
        (song_id,),
    )
    return [(r[0], r[1]) for r in cur.fetchall()]


@dataclass
class SetlistLayoutForSongRow:
    """Setlist that has a defined layout for the song (set has band_layout, song has SongLayout for that band)."""

    setlist_id: int
    setlist_name: str
    setlist_item_id: int
    band_layout_id: int
    song_layout_id: int


def get_setlists_with_layout_for_song(conn: sqlite3.Connection, song_id: int) -> list[SetlistLayoutForSongRow]:
    """Return setlists that contain this song and have a defined band layout where the song has a SongLayout."""
    cur = conn.execute(
        """SELECT sl.id, sl.name, si.id, sl.band_layout_id,
               COALESCE(
                 CASE WHEN si.song_layout_id IS NOT NULL AND slayout.band_layout_id = sl.band_layout_id
                   THEN si.song_layout_id ELSE NULL END,
                 (SELECT slo.id FROM SongLayout slo
                  WHERE slo.song_id = ? AND slo.band_layout_id = sl.band_layout_id
                  ORDER BY slo.name LIMIT 1)
               ) AS song_layout_id
           FROM Setlist sl
           JOIN SetlistItem si ON si.setlist_id = sl.id AND si.song_id = ?
           LEFT JOIN SongLayout slayout ON slayout.id = si.song_layout_id
           WHERE sl.band_layout_id IS NOT NULL
           AND EXISTS (
             SELECT 1 FROM SongLayout slo WHERE slo.song_id = ? AND slo.band_layout_id = sl.band_layout_id
           )
           ORDER BY sl.name""",
        (song_id, song_id, song_id),
    )
    return [
        SetlistLayoutForSongRow(
            setlist_id=r[0],
            setlist_name=r[1],
            setlist_item_id=r[2],
            band_layout_id=r[3],
            song_layout_id=r[4],
        )
        for r in cur.fetchall()
        if r[4] is not None
    ]


def add_setlist(conn: sqlite3.Connection, name: str, folder_id: int | None = None) -> int:
    from datetime import date
    now = _now()
    today = date.today().isoformat()
    default_time = "19:00"
    cur = conn.execute(
        """SELECT COALESCE(MAX(sort_order), -1) + 1 FROM Setlist WHERE folder_id IS ?""",
        (folder_id,),
    )
    next_order = cur.fetchone()[0]
    cur = conn.execute(
        """INSERT INTO Setlist (name, band_layout_id, folder_id, sort_order, locked, default_change_duration_seconds, notes,
                  set_date, set_time, target_duration_seconds, created_at, updated_at)
           VALUES (?, NULL, ?, ?, 0, NULL, NULL, ?, ?, NULL, ?, ?)""",
        (name.strip(), folder_id, next_order, today, default_time, now, now),
    )
    conn.commit()
    return cur.lastrowid


def update_setlist(
    conn: sqlite3.Connection,
    setlist_id: int,
    *,
    name: str | None = None,
    band_layout_id: Any = _UNSET,
    folder_id: Any = _UNSET,
    sort_order: Any = _UNSET,
    locked: bool | None = None,
    default_change_duration_seconds: Any = _UNSET,
    notes: Any = _UNSET,
    set_date: Any = _UNSET,
    set_time: Any = _UNSET,
    target_duration_seconds: Any = _UNSET,
) -> None:
    updates = []
    args = []
    if name is not None:
        updates.append("name = ?")
        args.append(name.strip())
    if band_layout_id is not _UNSET:
        updates.append("band_layout_id = ?")
        args.append(band_layout_id)
    if folder_id is not _UNSET:
        updates.append("folder_id = ?")
        args.append(folder_id)
    if sort_order is not _UNSET:
        updates.append("sort_order = ?")
        args.append(sort_order)
    if locked is not None:
        updates.append("locked = ?")
        args.append(1 if locked else 0)
    if default_change_duration_seconds is not _UNSET:
        updates.append("default_change_duration_seconds = ?")
        args.append(default_change_duration_seconds)
    if notes is not _UNSET:
        updates.append("notes = ?")
        args.append(notes if notes else None)
    if set_date is not _UNSET:
        updates.append("set_date = ?")
        args.append(set_date if set_date else None)
    if set_time is not _UNSET:
        updates.append("set_time = ?")
        args.append(set_time if set_time else None)
    if target_duration_seconds is not _UNSET:
        updates.append("target_duration_seconds = ?")
        args.append(target_duration_seconds)
    if not updates:
        return
    updates.append("updated_at = ?")
    args.append(_now())
    args.append(setlist_id)
    conn.execute(f"UPDATE Setlist SET {', '.join(updates)} WHERE id = ?", args)
    conn.commit()


def delete_setlist(conn: sqlite3.Connection, setlist_id: int) -> None:
    # Collect song_layout_ids from this setlist's items (before deletion)
    cur = conn.execute(
        "SELECT song_layout_id FROM SetlistItem WHERE setlist_id = ? AND song_layout_id IS NOT NULL",
        (setlist_id,),
    )
    song_layout_ids = [r[0] for r in cur.fetchall()]

    conn.execute(
        "UPDATE Song SET last_setlist_item_id = NULL "
        "WHERE last_setlist_item_id IN (SELECT id FROM SetlistItem WHERE setlist_id = ?)",
        (setlist_id,),
    )
    conn.execute(
        "DELETE FROM SetlistBandAssignment WHERE setlist_item_id IN (SELECT id FROM SetlistItem WHERE setlist_id = ?)",
        (setlist_id,),
    )
    conn.execute("DELETE FROM SetlistItem WHERE setlist_id = ?", (setlist_id,))
    conn.execute("DELETE FROM Setlist WHERE id = ?", (setlist_id,))

    # Delete song layouts that were only used by this setlist (now orphaned)
    for song_layout_id in song_layout_ids:
        cur = conn.execute(
            "SELECT 1 FROM SetlistItem WHERE song_layout_id = ? LIMIT 1", (song_layout_id,)
        )
        if cur.fetchone() is None:
            delete_song_layout(conn, song_layout_id)

    conn.commit()


def move_setlist_to_folder(
    conn: sqlite3.Connection,
    setlist_id: int,
    folder_id: int | None,
    sort_order: int,
) -> None:
    """Move setlist to folder (or None for Uncategorized) at given sort_order. Renumbers others in target folder."""
    now = _now()
    conn.execute(
        "UPDATE Setlist SET folder_id = ?, sort_order = ?, updated_at = ? WHERE id = ?",
        (folder_id, sort_order, now, setlist_id),
    )
    cur = conn.execute(
        "SELECT id FROM Setlist WHERE folder_id IS ? AND id != ? ORDER BY sort_order, name",
        (folder_id, setlist_id),
    )
    ids_in_order = [r[0] for r in cur.fetchall()]
    ids_in_order.insert(sort_order, setlist_id)
    for pos, sid in enumerate(ids_in_order):
        conn.execute(
            "UPDATE Setlist SET sort_order = ?, updated_at = ? WHERE id = ? AND folder_id IS ?",
            (pos, now, sid, folder_id),
        )
    conn.commit()


def reorder_setlists_in_folder(
    conn: sqlite3.Connection,
    folder_id: int | None,
    setlist_ids_in_order: list[int],
) -> None:
    """Set sort_order 0, 1, 2, ... for the given setlist ids in the folder."""
    now = _now()
    for pos, sid in enumerate(setlist_ids_in_order):
        conn.execute(
            "UPDATE Setlist SET sort_order = ?, updated_at = ? WHERE id = ? AND folder_id IS ?",
            (pos, now, sid, folder_id),
        )
    conn.commit()


def list_setlist_items(conn: sqlite3.Connection, setlist_id: int) -> list[tuple[SetlistItemRow, str]]:
    """Return (SetlistItemRow, song_title) for each item, ordered by position."""
    cur = conn.execute(
        """SELECT si.id, si.setlist_id, si.song_id, si.position, si.override_change_duration_seconds, si.song_layout_id, si.created_at, si.updated_at, s.title
           FROM SetlistItem si JOIN Song s ON s.id = si.song_id
           WHERE si.setlist_id = ? ORDER BY si.position""",
        (setlist_id,),
    )
    return [
        (
            SetlistItemRow(
                id=r[0],
                setlist_id=r[1],
                song_id=r[2],
                position=r[3],
                override_change_duration_seconds=r[4],
                song_layout_id=r[5],
                created_at=r[6],
                updated_at=r[7],
            ),
            r[8],
        )
        for r in cur.fetchall()
    ]


def list_setlist_items_with_song_meta(conn: sqlite3.Connection, setlist_id: int) -> list[SetlistItemSongMetaRow]:
    """Setlist items with song title, composers, duration, part count, parts JSON, transcriber, notes, status."""
    cur = conn.execute(
        """SELECT si.id, si.setlist_id, si.song_id, si.position, si.override_change_duration_seconds,
                  si.song_layout_id, si.created_at, si.updated_at,
                  s.title, s.composers, s.duration_seconds,
                  json_array_length(COALESCE(s.parts, '[]')), s.parts,
                  s.transcriber, s.notes, st.name
           FROM SetlistItem si
           JOIN Song s ON s.id = si.song_id
           LEFT JOIN Status st ON st.id = s.status_id
           WHERE si.setlist_id = ? ORDER BY si.position""",
        (setlist_id,),
    )
    rows = []
    for r in cur.fetchall():
        item = SetlistItemRow(
            id=r[0],
            setlist_id=r[1],
            song_id=r[2],
            position=r[3],
            override_change_duration_seconds=r[4],
            song_layout_id=r[5],
            created_at=r[6],
            updated_at=r[7],
        )
        rows.append(
            SetlistItemSongMetaRow(
                item=item,
                title=r[8],
                composers=r[9] or "",
                duration_seconds=r[10],
                part_count=int(r[11] or 0),
                parts_json=r[12],
                transcriber=r[13] if r[13] else None,
                notes=r[14] if r[14] else None,
                status_name=r[15] if r[15] else None,
            )
        )
    return rows


def add_setlist_item(
    conn: sqlite3.Connection,
    setlist_id: int,
    song_id: int,
    position: int,
    song_layout_id: int | None = None,
    override_change_duration_seconds: int | None = None,
) -> int:
    now = _now()
    cur = conn.execute(
        """INSERT INTO SetlistItem (setlist_id, song_id, position, override_change_duration_seconds, song_layout_id, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (setlist_id, song_id, position, override_change_duration_seconds, song_layout_id, now, now),
    )
    conn.commit()
    return cur.lastrowid


def update_setlist_item_position(conn: sqlite3.Connection, item_id: int, position: int) -> None:
    conn.execute("UPDATE SetlistItem SET position = ?, updated_at = ? WHERE id = ?", (position, _now(), item_id))
    conn.commit()


def update_setlist_item(
    conn: sqlite3.Connection,
    item_id: int,
    *,
    song_layout_id: Any = _UNSET,
    override_change_duration_seconds: Any = _UNSET,
) -> None:
    updates = []
    args = []
    if song_layout_id is not _UNSET:
        updates.append("song_layout_id = ?")
        args.append(song_layout_id)
    if override_change_duration_seconds is not _UNSET:
        updates.append("override_change_duration_seconds = ?")
        args.append(override_change_duration_seconds)
    if not updates:
        return
    updates.append("updated_at = ?")
    args.append(_now())
    args.append(item_id)
    conn.execute(f"UPDATE SetlistItem SET {', '.join(updates)} WHERE id = ?", args)
    conn.commit()


def remove_setlist_item(conn: sqlite3.Connection, item_id: int) -> None:
    conn.execute("UPDATE Song SET last_setlist_item_id = NULL WHERE last_setlist_item_id = ?", (item_id,))
    conn.execute("DELETE FROM SetlistBandAssignment WHERE setlist_item_id = ?", (item_id,))
    conn.execute("DELETE FROM SetlistItem WHERE id = ?", (item_id,))
    conn.commit()


def reorder_setlist_items(conn: sqlite3.Connection, setlist_id: int, item_ids_in_order: list[int]) -> None:
    """Set position 0,1,2,... for the given item ids in order."""
    now = _now()
    for pos, item_id in enumerate(item_ids_in_order):
        conn.execute(
            "UPDATE SetlistItem SET position = ?, updated_at = ? WHERE id = ? AND setlist_id = ?",
            (pos, now, item_id, setlist_id),
        )
    conn.commit()


def _next_duplicate_setlist_name(conn: sqlite3.Connection, source_name: str) -> str:
    prefix = f"Copy of {source_name.strip()}"
    existing = {s.name for s in list_setlists(conn)}
    if prefix not in existing:
        return prefix
    n = 2
    while f"{prefix} ({n})" in existing:
        n += 1
    return f"{prefix} ({n})"


def duplicate_setlist(conn: sqlite3.Connection, source_setlist_id: int) -> int:
    """Create a new setlist with the same folder, metadata, and copied items (including layouts and overrides)."""
    all_s = list_setlists(conn)
    source = next((s for s in all_s if s.id == source_setlist_id), None)
    if not source:
        raise ValueError("Setlist not found")
    new_name = _next_duplicate_setlist_name(conn, source.name)
    new_id = add_setlist(conn, new_name, folder_id=source.folder_id)
    update_setlist(
        conn,
        new_id,
        band_layout_id=source.band_layout_id,
        locked=source.locked,
        default_change_duration_seconds=source.default_change_duration_seconds,
        notes=source.notes,
        set_date=source.set_date,
        set_time=source.set_time,
        target_duration_seconds=source.target_duration_seconds,
    )
    if list_setlist_items(conn, source_setlist_id):
        merge_setlist_into(conn, new_id, source_setlist_id, prepend=False)
    return new_id


def merge_setlist_into(
    conn: sqlite3.Connection,
    target_setlist_id: int,
    source_setlist_id: int,
    prepend: bool,
    keep_band_layout_id: int | None = None,
    *,
    copy_item_details: bool = True,
) -> int:
    """
    Merge source setlist into target. Copies item rows in order (song_id and position).
    If copy_item_details is True (default): also copies per-item layout, change-duration override,
    and band assignments; may update target band layout when layouts differ and keep_band_layout_id
    is supplied.
    If copy_item_details is False: only song ids are copied; each new row uses the target setlist's
    band layout (get_or-create song layout) if the target has one, with no overrides or assignments.
    Target setlist metadata (name, dates, notes, …) is never modified.
    prepend=True: source items before target items.
    prepend=False: source items after target items.
    When copy_item_details is True and target and source have different band layouts,
    keep_band_layout_id must be provided.
    Returns number of items added.
    """
    all_setlists = {s.id: s for s in list_setlists(conn)}
    target_setlist = all_setlists.get(target_setlist_id)
    source_setlist = all_setlists.get(source_setlist_id)
    if not target_setlist or not source_setlist:
        return 0

    if not copy_item_details:
        target_items = list_setlist_items(conn, target_setlist_id)
        source_items = list_setlist_items(conn, source_setlist_id)
        if not source_items:
            return 0
        target_bl = target_setlist.band_layout_id
        target_item_ids = [item[0].id for item in target_items]
        new_item_ids: list[int] = []
        base_pos = 0 if prepend else len(target_item_ids)
        for i, (item_row, _) in enumerate(source_items):
            song_layout_id = (
                get_or_create_song_layout_for_band(conn, item_row.song_id, target_bl)
                if target_bl is not None
                else None
            )
            new_id = add_setlist_item(
                conn,
                target_setlist_id,
                item_row.song_id,
                position=base_pos + i,
                song_layout_id=song_layout_id,
                override_change_duration_seconds=None,
            )
            new_item_ids.append(new_id)
        if prepend:
            all_ids = new_item_ids + target_item_ids
        else:
            all_ids = target_item_ids + new_item_ids
        reorder_setlist_items(conn, target_setlist_id, all_ids)
        return len(new_item_ids)

    target_bl = target_setlist.band_layout_id
    source_bl = source_setlist.band_layout_id
    layouts_differ = target_bl != source_bl

    if layouts_differ and keep_band_layout_id is None:
        raise ValueError("Target and source have different band layouts; keep_band_layout_id required")

    target_items = list_setlist_items(conn, target_setlist_id)
    source_items = list_setlist_items(conn, source_setlist_id)
    if not source_items:
        return 0

    kept_bl = keep_band_layout_id if layouts_differ else target_bl

    if layouts_differ and kept_bl == source_bl:
        update_setlist(conn, target_setlist_id, band_layout_id=source_bl)
        for item_row, _ in target_items:
            new_layout_id = get_or_create_song_layout_for_band(conn, item_row.song_id, source_bl)
            update_setlist_item(conn, item_row.id, song_layout_id=new_layout_id)

    target_item_ids = [item[0].id for item in target_items]
    new_item_ids: list[int] = []
    base_pos = 0 if prepend else len(target_item_ids)

    for i, (item_row, _) in enumerate(source_items):
        if layouts_differ and kept_bl == target_bl:
            song_layout_id = get_or_create_song_layout_for_band(conn, item_row.song_id, target_bl)
            copy_assignments = False
        else:
            song_layout_id = item_row.song_layout_id
            copy_assignments = True

        new_id = add_setlist_item(
            conn,
            target_setlist_id,
            item_row.song_id,
            position=base_pos + i,
            song_layout_id=song_layout_id,
            override_change_duration_seconds=item_row.override_change_duration_seconds,
        )
        new_item_ids.append(new_id)
        if copy_assignments:
            for player_id, part_number in get_setlist_band_assignments(conn, item_row.id).items():
                upsert_setlist_band_assignment(conn, new_id, player_id, part_number)

    if prepend:
        all_ids = new_item_ids + target_item_ids
    else:
        all_ids = target_item_ids + new_item_ids
    reorder_setlist_items(conn, target_setlist_id, all_ids)
    return len(new_item_ids)


# --- SetlistBandAssignment (per-setlist-item player -> part overrides) ---


def get_setlist_band_assignments(conn: sqlite3.Connection, setlist_item_id: int) -> dict[int, int | None]:
    """Return {player_id: part_number or None} for explicit override rows."""
    cur = conn.execute(
        "SELECT player_id, part_number FROM SetlistBandAssignment WHERE setlist_item_id = ?",
        (setlist_item_id,),
    )
    return {r[0]: r[1] for r in cur.fetchall()}


def get_setlist_band_assignments_bulk(
    conn: sqlite3.Connection, setlist_item_ids: list[int]
) -> dict[int, dict[int, int | None]]:
    """Return setlist_item_id -> {player_id: part_number or None} for all given items."""
    if not setlist_item_ids:
        return {}
    placeholders = ",".join("?" * len(setlist_item_ids))
    cur = conn.execute(
        f"""SELECT setlist_item_id, player_id, part_number FROM SetlistBandAssignment
            WHERE setlist_item_id IN ({placeholders})""",
        setlist_item_ids,
    )
    result: dict[int, dict[int, int | None]] = {i: {} for i in setlist_item_ids}
    for r in cur.fetchall():
        sid, pid, pn = int(r[0]), int(r[1]), r[2]
        result.setdefault(sid, {})[pid] = pn
    return result


def upsert_setlist_band_assignment(
    conn: sqlite3.Connection,
    setlist_item_id: int,
    player_id: int,
    part_number: int | None,
) -> None:
    """Insert or update override for (setlist_item, player). part_number None = no part."""
    now = _now()
    cur = conn.execute(
        "SELECT id FROM SetlistBandAssignment WHERE setlist_item_id = ? AND player_id = ?",
        (setlist_item_id, player_id),
    )
    row = cur.fetchone()
    if row:
        conn.execute(
            "UPDATE SetlistBandAssignment SET part_number = ?, updated_at = ? WHERE id = ?",
            (part_number, now, row[0]),
        )
    else:
        conn.execute(
            """INSERT INTO SetlistBandAssignment (setlist_item_id, player_id, part_number, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?)""",
            (setlist_item_id, player_id, part_number, now, now),
        )
    conn.commit()


def delete_setlist_band_assignment(conn: sqlite3.Connection, setlist_item_id: int, player_id: int) -> None:
    """Remove override row so SongLayoutAssignment applies again for this player."""
    conn.execute(
        "DELETE FROM SetlistBandAssignment WHERE setlist_item_id = ? AND player_id = ?",
        (setlist_item_id, player_id),
    )
    conn.commit()
