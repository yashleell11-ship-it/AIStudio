import 'dart:collection';

import 'package:flutter/foundation.dart';

/// One chapter as the multi-select sees it — the least a range helper needs to
/// decide whether the chapter is worth queueing, and nothing about how the row
/// is drawn.
///
/// Deliberately not `SourceChapterSummary` or `KnownChapter`: the two series
/// pages hold different chapter models with different fields, and the whole
/// point of the helpers below is that "next 10" means the same thing on both.
typedef SelectableChapter = ({
  String key,
  double? number,
  String? title,

  /// Finished reading. "Next 10" and "All unread" skip these — the reader is
  /// downloading what comes *next*, not re-fetching what they already read.
  bool isRead,

  /// Already fully on the phone. Skipped by every helper: re-queueing it is a
  /// harmless no-op ([DownloadsStore.ensureQueued] is idempotent) but it would
  /// make "Next 10" select ten rows and download three, which reads as a bug.
  bool isDownloaded,
});

/// How many chapters the "Next N" quick range takes. Ten because that is the
/// number the owner asked for by name ("so i can download 10 chapters in 1
/// go") — the thing being replaced is ticking ten boxes by hand.
const int kQuickRangeChapterCount = 10;

/// Every chapter the reader has not finished and the phone does not already
/// have, **in the reading order it was given** — "All unread".
///
/// Reading order is the caller's responsibility (oldest first); this must not
/// re-sort, because the two series pages sort their visible list by the user's
/// Newest/Oldest toggle and "next" has to mean next-to-read regardless of
/// which way the list happens to be pointing.
List<String> unreadUndownloadedKeys(List<SelectableChapter> readingOrder) => [
      for (final chapter in readingOrder)
        if (!chapter.isRead && !chapter.isDownloaded) chapter.key,
    ];

/// "Next [count]" — the first [count] of exactly that list, so the two ranges
/// can never disagree about which chapters are candidates, only about how many.
List<String> nextUnreadUndownloadedKeys(
  List<SelectableChapter> readingOrder, {
  int count = kQuickRangeChapterCount,
}) =>
    unreadUndownloadedKeys(readingOrder).take(count).toList();

/// Everything not already on the phone, read or not — the "select all" range,
/// which exists because a reader re-reading a series wants the whole thing and
/// "unread" would hand them nothing.
List<String> undownloadedKeys(List<SelectableChapter> readingOrder) => [
      for (final chapter in readingOrder)
        if (!chapter.isDownloaded) chapter.key,
    ];

/// The multi-select state for one series' chapter list.
///
/// A plain [ChangeNotifier] owned by the screen rather than a provider: the
/// selection is a property of *this visit to this page*, and leaving the page
/// must forget it. A keyed provider would either leak the selection across
/// navigations or need explicit teardown at every exit, and the second one is
/// the bug that always gets missed.
class ChapterSelectionController extends ChangeNotifier {
  bool _active = false;
  final Set<String> _selected = <String>{};

  /// Whether the list is in multi-select mode. Rows only grow a checkbox while
  /// this is true — an untouched chapter list looks exactly as it always did.
  bool get isActive => _active;

  Set<String> get selected => UnmodifiableSetView(_selected);

  int get count => _selected.length;

  bool isSelected(String key) => _selected.contains(key);

  void begin() {
    if (_active) return;
    _active = true;
    notifyListeners();
  }

  /// Leaves multi-select and forgets the selection — one action, because a
  /// mode that exits with rows still ticked would re-enter holding a stale set
  /// the user cannot see.
  void end() {
    if (!_active && _selected.isEmpty) return;
    _active = false;
    _selected.clear();
    notifyListeners();
  }

  void toggle(String key) {
    if (!_selected.remove(key)) _selected.add(key);
    notifyListeners();
  }

  /// Applies a range helper's answer. Replaces rather than merges: "Next 10"
  /// tapped twice must select ten chapters, not twenty.
  void replaceWith(Iterable<String> keys) {
    _selected
      ..clear()
      ..addAll(keys);
    _active = true;
    notifyListeners();
  }

  void clearSelection() {
    if (_selected.isEmpty) return;
    _selected.clear();
    notifyListeners();
  }
}
