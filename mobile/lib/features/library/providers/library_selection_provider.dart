import 'package:flutter_riverpod/flutter_riverpod.dart';

/// Library multi-select state: whether selection mode is active, and which
/// series are currently checked. Kept separate from [active] (rather than
/// inferring "mode on" from a non-empty set) so entering selection mode via
/// the AppBar toggle can show an empty, ready-to-tap grid before anything
/// is selected.
class LibrarySelectionState {
  const LibrarySelectionState({this.active = false, this.selectedIds = const {}});

  final bool active;
  final Set<int> selectedIds;

  bool isSelected(int seriesId) => selectedIds.contains(seriesId);

  LibrarySelectionState copyWith({bool? active, Set<int>? selectedIds}) =>
      LibrarySelectionState(
        active: active ?? this.active,
        selectedIds: selectedIds ?? this.selectedIds,
      );
}

class LibrarySelectionController extends Notifier<LibrarySelectionState> {
  @override
  LibrarySelectionState build() => const LibrarySelectionState();

  void enterSelectionMode() => state = const LibrarySelectionState(active: true);

  /// Exits selection mode entirely and clears every checked item.
  void exitSelectionMode() => state = const LibrarySelectionState();

  void toggle(int seriesId) {
    final ids = {...state.selectedIds};
    if (!ids.remove(seriesId)) {
      ids.add(seriesId);
    }
    state = state.copyWith(selectedIds: ids);
  }

  void selectAll(Iterable<int> seriesIds) =>
      state = state.copyWith(selectedIds: seriesIds.toSet());

  void clearSelection() => state = state.copyWith(selectedIds: const {});
}

final librarySelectionProvider =
    NotifierProvider<LibrarySelectionController, LibrarySelectionState>(
  LibrarySelectionController.new,
  name: 'librarySelection',
);
