"""Tests for Set Play advance / skip scanning."""

from abc_music_manager.services.set_play_state import (
    SetPlaySessionState,
    advance_song,
    apply_exclusive_next,
    recompute_next_if_invalid,
    scan_next_item_id,
    toggle_skip,
)


def _ids(*xs: int) -> list[int]:
    return list(xs)


def test_scan_next_skips_skipped() -> None:
    order = _ids(10, 11, 12, 13)
    skipped = {11, 12}
    assert scan_next_item_id(order, skipped, after_index=0) == 13
    assert scan_next_item_id(order, skipped, after_index=-1) == 10


def test_scan_next_none_at_end() -> None:
    order = _ids(10, 11)
    assert scan_next_item_id(order, set(), after_index=1) is None


def test_advance_first_no_prior_current() -> None:
    st = SetPlaySessionState(order_item_ids=_ids(1, 2, 3), next_item_id=1)
    assert advance_song(st) is True
    assert st.current_item_id == 1
    assert st.played_item_ids == set()
    assert st.next_item_id == 2


def test_advance_moves_current_to_played() -> None:
    st = SetPlaySessionState(
        order_item_ids=_ids(1, 2, 3),
        current_item_id=1,
        next_item_id=2,
    )
    assert advance_song(st) is True
    assert 1 in st.played_item_ids
    assert st.current_item_id == 2
    assert st.next_item_id == 3


def test_advance_no_next_is_noop() -> None:
    st = SetPlaySessionState(order_item_ids=_ids(1, 2), current_item_id=1, next_item_id=None)
    r = advance_song(st)
    assert r is False
    assert st.current_item_id == 1


def test_advance_last_song_clears_next() -> None:
    st = SetPlaySessionState(order_item_ids=_ids(1, 2), current_item_id=1, next_item_id=2)
    assert advance_song(st) is True
    assert st.current_item_id == 2
    assert st.next_item_id is None


def test_advance_skips_skipped_rows_for_next() -> None:
    st = SetPlaySessionState(
        order_item_ids=_ids(1, 2, 3, 4),
        current_item_id=None,
        next_item_id=1,
        skipped_item_ids={2},
    )
    assert advance_song(st) is True
    assert st.current_item_id == 1
    assert st.next_item_id == 3


def test_skip_next_triggers_recompute() -> None:
    st = SetPlaySessionState(
        order_item_ids=_ids(1, 2, 3),
        current_item_id=1,
        next_item_id=2,
    )
    toggle_skip(st, 2)
    assert st.next_item_id == 3


def test_toggle_skip_on_non_next_does_not_clear_next() -> None:
    st = SetPlaySessionState(
        order_item_ids=_ids(1, 2, 3),
        current_item_id=1,
        next_item_id=2,
    )
    toggle_skip(st, 3)
    assert st.next_item_id == 2


def test_recompute_when_no_forward_candidate() -> None:
    st = SetPlaySessionState(
        order_item_ids=_ids(1, 2),
        current_item_id=1,
        next_item_id=2,
    )
    toggle_skip(st, 2)
    assert st.next_item_id is None


def test_apply_exclusive_next_clears_conflicting_current() -> None:
    st = SetPlaySessionState(order_item_ids=_ids(1, 2, 3), current_item_id=2, next_item_id=None)
    apply_exclusive_next(st, 2)
    assert st.current_item_id is None
    assert st.next_item_id == 2
