/**
 * Multi-select state for a list the user can shift-click through.
 *
 * Kept out of the view so the range math is testable on its own: shift-click is
 * the one part of a selection UI that is easy to get subtly wrong (backwards
 * ranges, a stale anchor that a filter change scrolled off the page) and
 * impossible to notice by eye until a bulk action hits the wrong 40 series.
 *
 * Generic over the id because two lists need exactly this behaviour and differ
 * only in what identifies a row: the library grid selects series by numeric id,
 * and a series page's chapter list selects chapters by their opaque string key
 * (`features/offline/chapter-selection.ts`). The half that is easy to get wrong
 * is the same in both, so there is one copy of it.
 *
 * `ids` is a Set because every card asks "am I selected?" on every render, and
 * the grid routinely holds 200 of them.
 */

export interface SelectionState<Id = number> {
  readonly ids: ReadonlySet<Id>;
  /**
   * The fixed end of a shift-click range: the last id clicked *without* shift.
   * `null` when nothing has been clicked yet, or when the anchor has since been
   * filtered out of the visible list.
   */
  readonly anchor: Id | null;
}

/** Holds no ids at all, so it is the empty selection of every id type. */
export const EMPTY_SELECTION: SelectionState<never> = {
  ids: new Set<never>(),
  anchor: null,
};

export function isSelected<Id>(state: SelectionState<Id>, id: Id): boolean {
  return state.ids.has(id);
}

export function selectionCount<Id>(state: SelectionState<Id>): number {
  return state.ids.size;
}

/**
 * The ids between `from` and `to` inclusive, in the order they are displayed.
 *
 * Order-agnostic: shift-clicking upwards has to select the same set as
 * shift-clicking downwards. Returns nothing when either end is missing from
 * `ordered`, which is the "anchor was filtered away" case.
 */
export function selectionRange<Id>(
  ordered: readonly Id[],
  from: Id,
  to: Id,
): Id[] {
  const start = ordered.indexOf(from);
  const end = ordered.indexOf(to);
  if (start === -1 || end === -1) {
    return [];
  }
  const [low, high] = start <= end ? [start, end] : [end, start];
  return ordered.slice(low, high + 1);
}

/** Plain click: flip one id and make it the anchor for the next shift-click. */
export function toggleSelection<Id>(
  state: SelectionState<Id>,
  id: Id,
): SelectionState<Id> {
  const ids = new Set(state.ids);
  if (ids.has(id)) {
    ids.delete(id);
  } else {
    ids.add(id);
  }
  // The anchor follows the last plain click even when that click deselected:
  // shift-clicking after "unselect this one" should still measure from here.
  return { ids, anchor: id };
}

/**
 * Shift-click: add the whole anchor→`id` range to what is already selected.
 *
 * Additive rather than replacing, like Gmail and the file managers people
 * already know: a shift-click never silently drops a selection built up
 * elsewhere in the grid. The anchor stays put so successive shift-clicks widen
 * or narrow the same range from a fixed end.
 *
 * With no usable anchor there is no range to take, so this degrades to a plain
 * click — the alternative is a click that appears to do nothing.
 */
export function extendSelection<Id>(
  state: SelectionState<Id>,
  id: Id,
  ordered: readonly Id[],
): SelectionState<Id> {
  if (state.anchor === null) {
    return toggleSelection(state, id);
  }
  const range = selectionRange(ordered, state.anchor, id);
  if (range.length === 0) {
    return toggleSelection(state, id);
  }
  const ids = new Set(state.ids);
  for (const rangeId of range) {
    ids.add(rangeId);
  }
  return { ids, anchor: state.anchor };
}

/** Select every visible id, anchoring on the first so shift-click still works. */
export function selectAll<Id>(ordered: readonly Id[]): SelectionState<Id> {
  return { ids: new Set(ordered), anchor: ordered[0] ?? null };
}

export function clearSelection<Id>(): SelectionState<Id> {
  return EMPTY_SELECTION;
}

/**
 * Drop everything no longer in `ordered`.
 *
 * Run whenever the visible set changes (a filter, a search, a refetch after a
 * bulk remove). Without it the selection keeps ids the user can no longer see,
 * and the next bulk action silently includes them — the count in the bar would
 * not even match the number of highlighted cards.
 *
 * Returns the same object when nothing was pruned so React can skip the render.
 */
export function retainSelection<Id>(
  state: SelectionState<Id>,
  ordered: readonly Id[],
): SelectionState<Id> {
  const visible = new Set(ordered);
  const kept = new Set<Id>();
  for (const id of state.ids) {
    if (visible.has(id)) {
      kept.add(id);
    }
  }
  const anchor = state.anchor !== null && visible.has(state.anchor) ? state.anchor : null;
  if (kept.size === state.ids.size && anchor === state.anchor) {
    return state;
  }
  return { ids: kept, anchor };
}

/** The selected ids in display order — the order bulk actions run them in. */
export function orderedSelection<Id>(
  state: SelectionState<Id>,
  ordered: readonly Id[],
): Id[] {
  return ordered.filter((id) => state.ids.has(id));
}
