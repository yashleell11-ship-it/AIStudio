import 'dart:async';

import 'package:aistudio_mobile/core/error/app_error.dart';
import 'package:aistudio_mobile/core/utils/result.dart';
import 'package:aistudio_mobile/features/updates/models/series_tracker.dart';
import 'package:aistudio_mobile/features/updates/models/update_notification.dart';
import 'package:aistudio_mobile/features/updates/providers/updates_provider.dart';
import 'package:aistudio_mobile/features/updates/repositories/updates_repository.dart';
import 'package:aistudio_mobile/shared/providers/repository_providers.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

/// Repository fake whose [deleteTracker] and [followSeries] can be held
/// pending via a [Completer], so tests can observe the notifier's state
/// mid-flight (before the network round-trip "completes").
class _FakeUpdatesRepository implements UpdatesRepository {
  _FakeUpdatesRepository({this.trackers = const []});

  List<SeriesTracker> trackers;
  Completer<void>? deleteGate;
  Completer<void>? followGate;
  int deleteCallCount = 0;
  int followCallCount = 0;

  @override
  Future<Result<void>> followSeries({
    required String source,
    required String seriesId,
    required String seriesTitle,
  }) async {
    followCallCount++;
    if (followGate != null) await followGate!.future;
    trackers = [
      ...trackers,
      SeriesTracker(
        id: 999,
        source: source,
        seriesId: seriesId,
        seriesTitle: seriesTitle,
        trackKind: TrackKind.followed,
        enabled: true,
        notify: true,
        autoDownload: false,
        knownChapterCount: 0,
      ),
    ];
    return const Ok(null);
  }

  @override
  Future<Result<void>> deleteTracker(int trackerId) async {
    deleteCallCount++;
    if (deleteGate != null) await deleteGate!.future;
    trackers = trackers.where((t) => t.id != trackerId).toList();
    return const Ok(null);
  }

  @override
  Future<Result<List<SeriesTracker>>> listTrackers() async => Ok(trackers);

  @override
  Future<Result<List<UpdateNotification>>> listNotifications({
    bool unreadOnly = false,
    int limit = 100,
  }) async =>
      const Ok([]);

  @override
  Future<Result<int>> getUnreadCount() async => const Ok(0);

  @override
  Future<Result<void>> markRead(int notificationId) async => const Ok(null);

  @override
  Future<Result<void>> markAllRead() async => const Ok(null);

  @override
  Future<Result<void>> triggerCheck() async => const Ok(null);
}

const _tracked = SeriesTracker(
  id: 42,
  source: 'mangadex',
  seriesId: 'series-1',
  seriesTitle: 'Solo Leveling',
  trackKind: TrackKind.followed,
  enabled: true,
  notify: true,
  autoDownload: false,
  knownChapterCount: 0,
);

void main() {
  group('UpdatesNotifier.trackerFor', () {
    test('returns the followed tracker for a matching source+series', () async {
      final repo = _FakeUpdatesRepository(trackers: [_tracked]);
      final container = ProviderContainer(
        overrides: [updatesRepositoryProvider.overrideWithValue(repo)],
      );
      addTearDown(container.dispose);

      await container.read(updatesProvider.future);
      final notifier = container.read(updatesProvider.notifier);

      final found = notifier.trackerFor(source: 'mangadex', seriesId: 'series-1');
      expect(found?.id, 42);
    });

    test('returns null for a series that is not followed', () async {
      final repo = _FakeUpdatesRepository(trackers: [_tracked]);
      final container = ProviderContainer(
        overrides: [updatesRepositoryProvider.overrideWithValue(repo)],
      );
      addTearDown(container.dispose);

      await container.read(updatesProvider.future);
      final notifier = container.read(updatesProvider.notifier);

      expect(
        notifier.trackerFor(source: 'mangadex', seriesId: 'series-does-not-exist'),
        isNull,
      );
      expect(
        notifier.trackerFor(source: 'asurascans', seriesId: 'series-1'),
        isNull,
      );
    });

    test('ignores a downloaded tracker for the same source+series id', () async {
      const downloaded = SeriesTracker(
        id: 7,
        source: 'mangadex',
        seriesId: 'series-1',
        seriesTitle: 'Solo Leveling',
        trackKind: TrackKind.downloaded,
        enabled: true,
        notify: false,
        autoDownload: true,
        knownChapterCount: 0,
      );
      final repo = _FakeUpdatesRepository(trackers: [downloaded]);
      final container = ProviderContainer(
        overrides: [updatesRepositoryProvider.overrideWithValue(repo)],
      );
      addTearDown(container.dispose);

      await container.read(updatesProvider.future);
      final notifier = container.read(updatesProvider.notifier);

      expect(notifier.trackerFor(source: 'mangadex', seriesId: 'series-1'), isNull);
    });
  });

  group('UpdatesNotifier.deleteTracker mirrors followSeries', () {
    test('sets actionPending immediately, then clears it once the delete resolves',
        () async {
      final repo = _FakeUpdatesRepository(trackers: [_tracked]);
      repo.deleteGate = Completer<void>();
      final container = ProviderContainer(
        overrides: [updatesRepositoryProvider.overrideWithValue(repo)],
      );
      addTearDown(container.dispose);

      await container.read(updatesProvider.future);
      final notifier = container.read(updatesProvider.notifier);

      expect(container.read(updatesProvider).valueOrNull?.actionPending, isFalse);

      final pending = notifier.deleteTracker(42);
      // Optimistic flag is set synchronously, before the repo call resolves.
      expect(container.read(updatesProvider).valueOrNull?.actionPending, isTrue);

      repo.deleteGate!.complete();
      await pending;

      expect(container.read(updatesProvider).valueOrNull?.actionPending, isFalse);
      expect(repo.deleteCallCount, 1);
    });

    test('clears actionPending on failure without leaving the button stuck busy',
        () async {
      final failingRepo = _FailingDeleteRepository(trackers: [_tracked]);
      final container = ProviderContainer(
        overrides: [updatesRepositoryProvider.overrideWithValue(failingRepo)],
      );
      addTearDown(container.dispose);

      await container.read(updatesProvider.future);
      final notifier = container.read(updatesProvider.notifier);

      final error = await notifier.deleteTracker(42);

      expect(error, isNotNull);
      expect(container.read(updatesProvider).valueOrNull?.actionPending, isFalse);
    });
  });
}

/// Repository whose [deleteTracker] always fails, to exercise the
/// error-recovery branch of [UpdatesNotifier.deleteTracker].
class _FailingDeleteRepository implements UpdatesRepository {
  _FailingDeleteRepository({this.trackers = const []});

  final List<SeriesTracker> trackers;

  @override
  Future<Result<void>> deleteTracker(int trackerId) async =>
      const Err(NetworkError(message: 'boom'));

  @override
  Future<Result<void>> followSeries({
    required String source,
    required String seriesId,
    required String seriesTitle,
  }) async =>
      const Ok(null);

  @override
  Future<Result<List<SeriesTracker>>> listTrackers() async => Ok(trackers);

  @override
  Future<Result<List<UpdateNotification>>> listNotifications({
    bool unreadOnly = false,
    int limit = 100,
  }) async =>
      const Ok([]);

  @override
  Future<Result<int>> getUnreadCount() async => const Ok(0);

  @override
  Future<Result<void>> markRead(int notificationId) async => const Ok(null);

  @override
  Future<Result<void>> markAllRead() async => const Ok(null);

  @override
  Future<Result<void>> triggerCheck() async => const Ok(null);
}
