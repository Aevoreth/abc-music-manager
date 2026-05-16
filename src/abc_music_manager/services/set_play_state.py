"""Set Play session state: advance rules, next scan, skip recompute (unit-tested)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SetPlaySessionState:
    """Item ids index into the ordered setlist; flags use SetlistItem.id."""

    order_item_ids: list[int]
    played_item_ids: set[int] = field(default_factory=set)
    current_item_id: int | None = None
    next_item_id: int | None = None
    skipped_item_ids: set[int] = field(default_factory=set)
    revision: int = 0

    def item_index(self, item_id: int) -> int:
        return self.order_item_ids.index(item_id)


def scan_next_item_id(
    order: list[int],
    skipped: set[int],
    *,
    after_index: int,
) -> int | None:
    """First item id after `after_index` that is not in `skipped`. No wrap."""
    for i in range(after_index + 1, len(order)):
        iid = order[i]
        if iid not in skipped:
            return iid
    return None


def recompute_next_if_invalid(state: SetPlaySessionState) -> bool:
    """
    If next is missing, skipped, or not in order, set next by scanning after current.
    Returns True if state.next_item_id changed.
    """
    order = state.order_item_ids
    skipped = state.skipped_item_ids
    cur = state.current_item_id
    nxt = state.next_item_id

    def find_next() -> int | None:
        if cur is None:
            return scan_next_item_id(order, skipped, after_index=-1)
        try:
            idx = order.index(cur)
        except ValueError:
            return scan_next_item_id(order, skipped, after_index=-1)
        return scan_next_item_id(order, skipped, after_index=idx)

    if nxt is None:
        return False
    if nxt not in order or nxt in skipped:
        new_n = find_next()
        if new_n != nxt:
            state.next_item_id = new_n
            return True
        return False
    return False


def advance_song(state: SetPlaySessionState) -> bool:
    """
    Advance one song. Precondition: next_item_id must be set; otherwise no-op (returns False).
    - Current (if any) goes to played.
    - Previous next becomes current.
    - Next becomes first non-skipped row after new current, or None at end of set.
    """
    if state.next_item_id is None:
        return False
    order = state.order_item_ids
    nxt = state.next_item_id
    if nxt not in order:
        return False

    if state.current_item_id is not None:
        state.played_item_ids.add(state.current_item_id)

    try:
        cur_idx = order.index(nxt)
    except ValueError:
        return False

    state.current_item_id = nxt
    state.next_item_id = scan_next_item_id(order, state.skipped_item_ids, after_index=cur_idx)
    state.revision += 1
    return True


def apply_exclusive_current(state: SetPlaySessionState, item_id: int | None) -> None:
    """Set current row (checkbox); None clears. Mutually exclusive with next on same row."""
    if state.current_item_id == item_id:
        return
    state.current_item_id = item_id
    if item_id is not None and state.next_item_id == item_id:
        state.next_item_id = None
    state.revision += 1


def apply_exclusive_next(state: SetPlaySessionState, item_id: int | None) -> None:
    """Set next row; None clears. Mutually exclusive with current on same row."""
    if state.next_item_id == item_id:
        return
    state.next_item_id = item_id
    if item_id is not None and state.current_item_id == item_id:
        state.current_item_id = None
    state.revision += 1


def toggle_played(state: SetPlaySessionState, item_id: int) -> None:
    if item_id in state.played_item_ids:
        state.played_item_ids.discard(item_id)
    else:
        state.played_item_ids.add(item_id)
    state.revision += 1


def toggle_skip(state: SetPlaySessionState, item_id: int) -> None:
    if item_id in state.skipped_item_ids:
        state.skipped_item_ids.discard(item_id)
    else:
        state.skipped_item_ids.add(item_id)
    recompute_next_if_invalid(state)
    state.revision += 1
