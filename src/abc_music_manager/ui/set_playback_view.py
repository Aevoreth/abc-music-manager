"""
Set Playback mode: leader view — current/next song, band layout, mark played, advance.
REQUIREMENTS §7. LAN sync via WebSocket (DECISIONS 015 Phase 1).
"""

from __future__ import annotations

import json

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QComboBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QGroupBox,
    QMessageBox,
)
from PySide6.QtCore import Qt, QObject, Signal

from ..services.app_state import AppState
from ..services.playback_state import PlaybackState, PlaylistEntry
from ..db.setlist_repo import list_setlists, list_setlist_items, get_setlist_band_assignments
from ..db.library_query import get_primary_file_path_for_song
from ..services.preferences import resolve_music_path
from ..db.song_layout_repo import get_song_layout_assignments
from ..db import get_instrument_name
from ..db.band_repo import list_layout_slots
from ..db.player_repo import list_players


def _get_next_song_layout_slots(conn, setlist_item_id: int) -> list[tuple[str, int | None, str]]:
    """Return (player_name, part_number, instrument_name) for the next item's song layout."""
    cur = conn.execute(
        """SELECT si.song_layout_id, si.song_id FROM SetlistItem si WHERE si.id = ?""",
        (setlist_item_id,),
    )
    row = cur.fetchone()
    if not row or not row[0]:
        return []
    song_layout_id, song_id = row[0], row[1]
    assignments = get_song_layout_assignments(conn, song_layout_id)
    overrides = get_setlist_band_assignments(conn, setlist_item_id)
    parts_json = conn.execute("SELECT parts FROM Song WHERE id = ?", (song_id,)).fetchone()
    parts = json.loads(parts_json[0]) if parts_json and parts_json[0] else []
    parts_by_num = {p["part_number"]: p for p in parts}
    players = {p.id: p.name for p in list_players(conn)}
    result = []
    for a in assignments:
        player_name = players.get(a.player_id, str(a.player_id))
        if a.player_id in overrides:
            part_num = overrides[a.player_id]
        else:
            part_num = a.part_number
        instrument_name = "—"
        if part_num is not None and part_num in parts_by_num:
            iid = parts_by_num[part_num].get("instrument_id")
            if iid:
                instrument_name = get_instrument_name(conn, iid) or "—"
        result.append((player_name, part_num, instrument_name))
    return result


class SetPlaybackView(QWidget):
    """Leader view: select setlist, show current/next, band layout for next, mark played."""

    def __init__(
        self,
        app_state: AppState,
        playback_state: PlaybackState | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.app_state = app_state
        self.playback_state = playback_state
        self._setlist_id: int | None = None
        self._current_index: int = -1  # last played index
        self._next_index: int = 0
        layout = QVBoxLayout(self)

        h = QHBoxLayout()
        h.addWidget(QLabel("Setlist:"))
        self.setlist_combo = QComboBox()
        self.setlist_combo.addItem("(select setlist)", None)
        for s in list_setlists(self.app_state.conn):
            if s.band_layout_id and not s.locked:
                self.setlist_combo.addItem(s.name, s.id)
        self.setlist_combo.currentIndexChanged.connect(self._on_setlist_changed)
        h.addWidget(self.setlist_combo)
        self.start_btn = QPushButton("Start")
        self.start_btn.clicked.connect(self._start)
        h.addWidget(self.start_btn)
        layout.addLayout(h)

        self.songs_group = QGroupBox("Setlist items")
        self.songs_table = QTableWidget()
        self.songs_table.setColumnCount(5)
        self.songs_table.setHorizontalHeaderLabels(["", "#", "Song", "Status", "Layout"])
        self.songs_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.songs_table.itemSelectionChanged.connect(self._on_selection_changed)
        self.songs_table.cellClicked.connect(self._on_cell_clicked)
        slayout = QVBoxLayout(self.songs_group)
        slayout.addWidget(self.songs_table)
        layout.addWidget(self.songs_group)
        self.songs_group.setEnabled(False)

        btn_layout = QHBoxLayout()
        self.mark_played_btn = QPushButton("Mark current as played")
        self.mark_played_btn.clicked.connect(self._mark_played)
        self.mark_played_btn.setEnabled(False)
        btn_layout.addWidget(self.mark_played_btn)
        layout.addLayout(btn_layout)

        self.layout_group = QGroupBox("Next song — band layout (player / part / instrument)")
        self.layout_table = QTableWidget()
        self.layout_table.setColumnCount(3)
        self.layout_table.setHorizontalHeaderLabels(["Player", "Part", "Instrument"])
        llayout = QVBoxLayout(self.layout_group)
        llayout.addWidget(self.layout_table)
        layout.addWidget(self.layout_group)
        self.layout_group.setEnabled(False)

    def _on_setlist_changed(self) -> None:
        self._setlist_id = self.setlist_combo.currentData()
        self._current_index = -1
        self._next_index = 0
        self._refresh_songs()

    def _start(self) -> None:
        self._setlist_id = self.setlist_combo.currentData()
        if not self._setlist_id:
            QMessageBox.warning(self, "Setlist", "Select a setlist with a band layout first.")
            return
        setlist = next(s for s in list_setlists(self.app_state.conn) if s.id == self._setlist_id)
        if not setlist.band_layout_id:
            QMessageBox.warning(self, "Setlist", "This setlist has no band layout. Set one in Setlists.")
            return
        self._current_index = -1
        self._next_index = 0
        self.songs_group.setEnabled(True)
        self.layout_group.setEnabled(True)
        self._refresh_songs()
        self._refresh_next_layout()

    def _refresh_songs(self) -> None:
        if not self._setlist_id:
            return
        items_with_titles = list_setlist_items(self.app_state.conn, self._setlist_id)
        self.songs_table.setRowCount(len(items_with_titles))
        for i, (item, song_title) in enumerate(items_with_titles):
            self.songs_table.setItem(i, 0, QTableWidgetItem("▶"))
            self.songs_table.setItem(i, 1, QTableWidgetItem(str(i + 1)))
            self.songs_table.setItem(i, 2, QTableWidgetItem(song_title))
            status = ""
            if i == self._current_index:
                status = "Last played"
            elif i == self._next_index:
                status = "Next"
            self.songs_table.setItem(i, 3, QTableWidgetItem(status))
            layout_name = "—"
            if item.song_layout_id:
                r = self.app_state.conn.execute("SELECT name FROM SongLayout WHERE id = ?", (item.song_layout_id,)).fetchone()
                layout_name = r[0] if r and r[0] else str(item.song_layout_id)
            self.songs_table.setItem(i, 4, QTableWidgetItem(layout_name))
            for c in range(5):
                cell = self.songs_table.item(i, c)
                if cell:
                    if i == self._current_index:
                        cell.setBackground(Qt.GlobalColor.darkGreen)
                    elif i == self._next_index:
                        cell.setBackground(Qt.GlobalColor.darkBlue)
        self.songs_table.setRowCount(len(items_with_titles))
        self.mark_played_btn.setEnabled(self._next_index < len(items_with_titles))
        self._refresh_next_layout()

    def _on_cell_clicked(self, row: int, col: int) -> None:
        if col == 0 and self.playback_state and self._setlist_id:
            self._play_from_setlist(row)

    def _play_from_setlist(self, start_index: int) -> None:
        """Load setlist into playlist, start from start_index, use setlist band layout."""
        if not self.playback_state or not self._setlist_id:
            return
        items_with_titles = list_setlist_items(self.app_state.conn, self._setlist_id)
        setlist = next(s for s in list_setlists(self.app_state.conn) if s.id == self._setlist_id)
        entries = []
        for item, song_title in items_with_titles:
            fp = get_primary_file_path_for_song(self.app_state.conn, item.song_id)
            if fp:
                fp = resolve_music_path(fp) or fp
                entries.append(PlaylistEntry(song_id=item.song_id, file_path=fp, title=song_title, source="set_playback"))
        if not entries:
            return
        self.playback_state.active_band_layout_id = setlist.band_layout_id
        self.playback_state.replace_playlist(entries, start_index=start_index)

    def _on_selection_changed(self) -> None:
        row = self.songs_table.currentRow()
        if row >= 0 and self._setlist_id:
            self._next_index = row
            self._refresh_songs()

    def _refresh_next_layout(self) -> None:
        if not self._setlist_id:
            return
        items_with_titles = list_setlist_items(self.app_state.conn, self._setlist_id)
        if self._next_index >= len(items_with_titles):
            self.layout_table.setRowCount(0)
            return
        item = items_with_titles[self._next_index][0]
        slots = _get_next_song_layout_slots(self.app_state.conn, item.id)
        self.layout_table.setRowCount(len(slots))
        for i, (player_name, part_num, instrument_name) in enumerate(slots):
            self.layout_table.setItem(i, 0, QTableWidgetItem(player_name))
            self.layout_table.setItem(i, 1, QTableWidgetItem(str(part_num) if part_num is not None else "None"))
            self.layout_table.setItem(i, 2, QTableWidgetItem(instrument_name))
        self.layout_table.setRowCount(len(slots))

    def _mark_played(self) -> None:
        if not self._setlist_id:
            return
        items_with_titles = list_setlist_items(self.app_state.conn, self._setlist_id)
        if self._next_index >= len(items_with_titles):
            return
        from ..db.play_log import log_play
        item = items_with_titles[self._next_index][0]
        log_play(self.app_state.conn, item.song_id, context_setlist_id=self._setlist_id)
        self._current_index = self._next_index
        self._next_index = min(self._next_index + 1, len(items_with_titles))
        self._refresh_songs()