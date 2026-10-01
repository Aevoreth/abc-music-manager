"""Song detail and layout-editor dialog sizes."""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication, QDialog

from abc_music_manager.services.preferences import (
    SONG_DETAIL_DIALOG_MIN_HEIGHT,
    SONG_DETAIL_DIALOG_MIN_WIDTH,
    SONG_LAYOUT_EDITOR_DIALOG_MIN_HEIGHT,
    get_song_detail_dialog_size,
    get_song_layout_editor_dialog_size,
    set_song_detail_dialog_size,
    set_song_layout_editor_dialog_size,
)
from abc_music_manager.ui.dialog_size import RememberDialogSize, layout_editor_size_for_slots


@pytest.fixture
def data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("ABC_MUSIC_MANAGER_DATA", str(tmp_path))
    (tmp_path / "abc_music_manager.sqlite").write_bytes(b"")
    return tmp_path


@pytest.fixture
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_dialog_size_prefs_round_trip(data_dir: Path) -> None:
    assert get_song_detail_dialog_size() is None
    set_song_detail_dialog_size(1100, 800)
    assert get_song_detail_dialog_size() == {"width": 1100, "height": 800}

    set_song_detail_dialog_size(SONG_DETAIL_DIALOG_MIN_WIDTH - 1, 800)
    assert get_song_detail_dialog_size() == {"width": 1100, "height": 800}

    set_song_layout_editor_dialog_size(1400, 900)
    assert get_song_layout_editor_dialog_size() == {"width": 1400, "height": 900}
    set_song_layout_editor_dialog_size(1400, SONG_LAYOUT_EDITOR_DIALOG_MIN_HEIGHT - 1)
    assert get_song_layout_editor_dialog_size() == {"width": 1400, "height": 900}


def test_layout_editor_size_uses_floor_for_small_grids() -> None:
    # 6 cards × 9 units by 3 cards × 7 units at 15 px — the old fixed 950×520 window.
    positions = [(x * 9, y * 7) for y in range(3) for x in range(6)]
    assert layout_editor_size_for_slots(
        positions,
        card_width=9,
        card_height=7,
        pixels_per_unit=15,
        floor_width=950,
        floor_height=520,
    ) == (950, 520)


def test_layout_editor_size_grows_for_wide_grids() -> None:
    positions = [(0, 0), (80, 0), (0, 40)]
    width, height = layout_editor_size_for_slots(
        positions,
        card_width=9,
        card_height=7,
        pixels_per_unit=15,
        floor_width=950,
        floor_height=520,
    )
    assert width == (80 + 9) * 15 + 64
    assert height == (40 + 7) * 15 + 200
    assert width > 950
    assert height > 520


def test_dialog_remembers_user_resize(data_dir: Path, qapp: QApplication) -> None:
    class SizedDialog(RememberDialogSize, QDialog):
        def __init__(self) -> None:
            super().__init__()
            self.setMinimumSize(SONG_DETAIL_DIALOG_MIN_WIDTH, SONG_DETAIL_DIALOG_MIN_HEIGHT)
            self._begin_size_memory(
                get_song_detail_dialog_size(),
                1040,
                740,
                set_song_detail_dialog_size,
            )

    first = SizedDialog()
    first.show()
    qapp.processEvents()
    assert (first.width(), first.height()) == (1040, 740)
    first.accept()
    assert get_song_detail_dialog_size() is None

    second = SizedDialog()
    second.show()
    qapp.processEvents()
    second.resize(1280, 860)
    qapp.processEvents()
    second.accept()
    assert get_song_detail_dialog_size() == {"width": 1280, "height": 860}

    third = SizedDialog()
    assert (third.width(), third.height()) == (1280, 860)
    third.deleteLater()
    second.deleteLater()
    first.deleteLater()
