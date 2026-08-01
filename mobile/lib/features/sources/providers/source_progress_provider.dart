import 'dart:convert';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:manhwamaniacs/features/profiles/providers/profiles_providers.dart';
import 'package:manhwamaniacs/features/sources/models/source_chapter_progress.dart';
import 'package:manhwamaniacs/shared/providers/core_providers.dart';

/// SharedPreferences key prefix holding the full source-progress map as a JSON
/// object mapping `"sourceId:seriesId:chapterId"` → the progress record. The
/// live storage key is namespaced per active profile (`"$prefix:$profileId"`)
/// so personas never read or overwrite each other's online-read state. Shared
/// cross-platform contract — the web client writes the identical record shape.
const String sourceProgressPrefsKey = 'mm.source_progress';

/// Composite storage key for a single online chapter's progress record.
String sourceProgressKey({
  required String sourceId,
  required String seriesId,
  required String chapterId,
}) =>
    '$sourceId:$seriesId:$chapterId';

/// The latest-read chapter for a series and its progress record.
typedef LatestSourceRead = ({String chapterId, SourceChapterProgress progress});

/// Holds the decoded source-progress map, hydrated from SharedPreferences.
///
/// Online source chapters have no server-side read/progress model, so this
/// store is the mobile side of the shared client-side contract (see
/// [SourceChapterProgress]). It backs the "read" row styling, per-row progress
/// text, and the "Continue" vs "Read Online" primary action on the series
/// detail screen.
class SourceProgressNotifier
    extends Notifier<Map<String, SourceChapterProgress>> {
  /// Per-profile storage key resolved in [build]; `null` when no profile is
  /// active (nothing is persisted in that state).
  String? _key;

  @override
  Map<String, SourceChapterProgress> build() {
    final prefs = ref.watch(sharedPrefsProvider);
    // Watching the active profile namespaces the store *and* self-rebuilds on
    // a profile switch: the incoming persona re-reads its own records while the
    // outgoing one's drop off screen.
    final profileId = ref.watch(activeProfileProvider)?.id;
    if (profileId == null) {
      _key = null;
      return const {};
    }
    final key = '$sourceProgressPrefsKey:$profileId';
    _key = key;
    final raw = prefs.getString(key);
    if (raw == null || raw.isEmpty) return const {};
    try {
      final decoded = jsonDecode(raw) as Map<String, dynamic>;
      return {
        for (final entry in decoded.entries)
          entry.key: SourceChapterProgress.fromJson(
            entry.value as Map<String, dynamic>,
          ),
      };
    } catch (_) {
      // Corrupt payload — start clean rather than crashing the screen.
      return const {};
    }
  }

  /// Persist the current page for a chapter. Marks the record completed when
  /// [page] reaches [pageCount] (with ``pageCount > 0``) and stamps
  /// ``updatedAt`` so the latest-read lookup can find the most recent chapter.
  Future<void> record({
    required String sourceId,
    required String seriesId,
    required String chapterId,
    required int page,
    required int pageCount,
  }) async {
    final safePage = page < 1 ? 1 : page;
    final entry = SourceChapterProgress(
      page: safePage,
      pageCount: pageCount,
      completed: pageCount > 0 && safePage >= pageCount,
      updatedAt: DateTime.now().toUtc(),
    );
    final key = sourceProgressKey(
      sourceId: sourceId,
      seriesId: seriesId,
      chapterId: chapterId,
    );
    final next = {...state, key: entry};
    state = next;
    await _persist(next);
  }

  /// Replay a migration's chapter map over this store, returning how many
  /// records carried over.
  ///
  /// Online reading progress for a non-downloaded remote series exists only
  /// here — the server has no read model for it — so a migration that did not
  /// do this would repoint the tracker and silently lose the reader's place.
  ///
  /// Three rules, matching the web's `applyProgressRemap` so both clients agree
  /// about the shared store:
  ///
  ///  * **Copies, never moves.** The records under the old (source, series) are
  ///    left alone, so migrating back loses nothing and replaying the same map
  ///    is a no-op.
  ///  * A chapter with no target (`toChapterId == null`) is skipped — there is
  ///    nowhere to put it.
  ///  * A target that already holds *newer* progress is never overwritten.
  ///    Nearest-match can collapse two old chapters onto one target, and the
  ///    most recently read of them is the one that says where the reader is.
  Future<int> remapSeriesProgress({
    required String fromSourceId,
    required String fromSeriesId,
    required String toSourceId,
    required String toSeriesId,
    required Map<String, String> carriedChapterIds,
  }) async {
    final next = {...state};
    var carried = 0;

    for (final entry in carriedChapterIds.entries) {
      final source = next[sourceProgressKey(
        sourceId: fromSourceId,
        seriesId: fromSeriesId,
        chapterId: entry.key,
      )];
      if (source == null) continue;

      final targetKey = sourceProgressKey(
        sourceId: toSourceId,
        seriesId: toSeriesId,
        chapterId: entry.value,
      );
      final existing = next[targetKey];
      if (existing != null && !existing.updatedAt.isBefore(source.updatedAt)) {
        continue;
      }

      next[targetKey] = source;
      carried += 1;
    }

    if (carried == 0) return 0;
    state = next;
    await _persist(next);
    return carried;
  }

  Future<void> _persist(Map<String, SourceChapterProgress> map) async {
    final key = _key;
    if (key == null) return;
    final prefs = ref.read(sharedPrefsProvider);
    final encoded = jsonEncode(
      map.map((key, value) => MapEntry(key, value.toJson())),
    );
    await prefs.setString(key, encoded);
  }

  /// Progress for a single chapter, or ``null`` when never opened.
  SourceChapterProgress? progressFor({
    required String sourceId,
    required String seriesId,
    required String chapterId,
  }) =>
      state[sourceProgressKey(
        sourceId: sourceId,
        seriesId: seriesId,
        chapterId: chapterId,
      )];

  /// Progress records for one series, keyed by chapter id.
  Map<String, SourceChapterProgress> forSeries({
    required String sourceId,
    required String seriesId,
  }) {
    final prefix = '$sourceId:$seriesId:';
    return {
      for (final entry in state.entries)
        if (entry.key.startsWith(prefix))
          entry.key.substring(prefix.length): entry.value,
    };
  }

  /// The most recently read chapter for a series (max ``updatedAt``), or
  /// ``null`` when the series has no progress yet.
  LatestSourceRead? latestForSeries({
    required String sourceId,
    required String seriesId,
  }) {
    MapEntry<String, SourceChapterProgress>? best;
    for (final entry in forSeries(sourceId: sourceId, seriesId: seriesId)
        .entries) {
      if (best == null || entry.value.updatedAt.isAfter(best.value.updatedAt)) {
        best = entry;
      }
    }
    if (best == null) return null;
    return (chapterId: best.key, progress: best.value);
  }
}

final sourceProgressProvider =
    NotifierProvider<SourceProgressNotifier, Map<String, SourceChapterProgress>>(
  SourceProgressNotifier.new,
  name: 'sourceProgress',
);
