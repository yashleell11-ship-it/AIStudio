// Regression cover for the data-layer audit's outbox findings.
//
// OUTBOX-1  two overlapping flushes read the same outbox rows and sent them
//           twice; the server ACCUMULATES `time_spent_seconds`, so every
//           extra flush inflated the reading-time statistic.
// OUTBOX-2  a bookmark sync in flight across a profile switch merged the
//           listing into the store it was constructed for — the profile that
//           is no longer active.
// OUTBOX-4  every offline save re-read and JSON-decoded the entire outbox for
//           a POST that could not land, and the outbox itself was unbounded:
//           an offline evening cost O(saves²).

import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/core/error/app_error.dart';
import 'package:manhwamaniacs/core/utils/result.dart';
import 'package:manhwamaniacs/features/downloads/providers/bookmark_outbox_provider.dart';
import 'package:manhwamaniacs/features/downloads/providers/downloads_scope.dart';
import 'package:manhwamaniacs/features/downloads/providers/progress_outbox_provider.dart';
import 'package:manhwamaniacs/features/downloads/store/bookmarks_dao.dart';
import 'package:manhwamaniacs/features/downloads/store/downloads_store.dart';
import 'package:manhwamaniacs/features/downloads/utils/progress_outbox_batch.dart';
import 'package:manhwamaniacs/features/profiles/models/mood.dart';
import 'package:manhwamaniacs/features/profiles/models/profile.dart';
import 'package:manhwamaniacs/features/profiles/providers/profiles_providers.dart';
import 'package:manhwamaniacs/features/reader/models/bookmark.dart';
import 'package:manhwamaniacs/features/reader/models/reading_progress.dart';
import 'package:manhwamaniacs/features/reader/repositories/reader_repository.dart';
import 'package:manhwamaniacs/shared/providers/core_providers.dart';
import 'package:manhwamaniacs/shared/providers/repository_providers.dart';
import 'package:mocktail/mocktail.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../support/downloads_test_support.dart';
import '../support/test_overrides.dart';

class _Repo extends Mock implements ReaderRepository {}

/// Counts full outbox reads — the per-save cost OUTBOX-4 is about, measured
/// structurally rather than with a stopwatch.
class _CountingStore extends DownloadsStore {
  _CountingStore(DownloadsStore inner)
      : super(
          scopeId: inner.scopeId,
          database: inner.database,
          blobStore: inner.blobStore,
        );

  int outboxReads = 0;

  @override
  Future<List<(int, ProgressPush)>> pendingProgressOutbox() {
    outboxReads++;
    return super.pendingProgressOutbox();
  }
}

/// A store whose outbox read parks until released, so a profile switch can be
/// landed in the window between the drain reading rows and posting them.
class _PausingStore extends DownloadsStore {
  _PausingStore(DownloadsStore inner)
      : super(
          scopeId: inner.scopeId,
          database: inner.database,
          blobStore: inner.blobStore,
        );

  final Completer<void> reading = Completer<void>();
  final Completer<void> release = Completer<void>();

  @override
  Future<List<(int, ProgressPush)>> pendingProgressOutbox() async {
    if (!reading.isCompleted) reading.complete();
    await release.future;
    return super.pendingProgressOutbox();
  }
}

ProgressPush _push({required int timeSpent, int lastPage = 5}) =>
    ProgressPush(
      sourceId: 'asura',
      seriesKey: 'solo-leveling',
      chapterKey: '1',
      chapterNumber: 1,
      lastPage: lastPage,
      pageCount: 20,
      timeSpentSeconds: timeSpent,
    );

void main() {
  initSqfliteFfiForTests();
  setUpAll(() => registerFallbackValue(<ProgressPush>[]));

  late TestDownloadsHarness harness;
  setUp(() async => harness = await TestDownloadsHarness.create());
  tearDown(() async => harness.dispose());

  group('OUTBOX-1 progress outbox re-send', () {
    test('overlapping flushes deliver each queued delta exactly once',
        () async {
      final repo = _Repo();
      final firstPostStarted = Completer<void>();
      final releaseFirstPost = Completer<void>();
      final sent = <List<ProgressPush>>[];
      var calls = 0;
      when(() => repo.saveProgressBatch(any())).thenAnswer((inv) async {
        sent.add(inv.positionalArguments.first as List<ProgressPush>);
        if (++calls == 1) {
          firstPostStarted.complete();
          // A slow link: the first POST is still in flight when the reader's
          // next save and the lifecycle gate's own trigger call flush().
          await releaseFirstPost.future;
        }
        return const Ok((saved: 1, advanced: 1));
      });

      final store = harness.storeFor('u1p1');
      final container = ProviderContainer(
        overrides: [
          downloadsStoreProvider.overrideWithValue(store),
          readerRepositoryProvider.overrideWithValue(repo),
        ],
      );
      addTearDown(container.dispose);
      final controller = container.read(progressOutboxControllerProvider);

      await store.enqueueProgress(_push(timeSpent: 30));

      final flushA = controller.flush();
      await firstPostStarted.future;
      final flushB = controller.flush();
      releaseFirstPost.complete();
      await Future.wait([flushA, flushB]);

      expect(await store.pendingProgressOutbox(), isEmpty);
      expect(
        sent.expand((b) => b).fold<int>(0, (a, p) => a + p.timeSpentSeconds),
        30,
        reason: 'one 30 s delta reached the server ${sent.length} times; the '
            'server adds each copy to the stored total',
      );
    });

    test('a row queued while a flush is in flight still goes out', () async {
      final repo = _Repo();
      final firstPostStarted = Completer<void>();
      final releaseFirstPost = Completer<void>();
      final sent = <List<ProgressPush>>[];
      var calls = 0;
      when(() => repo.saveProgressBatch(any())).thenAnswer((inv) async {
        sent.add(inv.positionalArguments.first as List<ProgressPush>);
        if (++calls == 1) {
          firstPostStarted.complete();
          await releaseFirstPost.future;
        }
        return const Ok((saved: 1, advanced: 1));
      });

      final store = harness.storeFor('u1p1');
      final container = ProviderContainer(
        overrides: [
          downloadsStoreProvider.overrideWithValue(store),
          readerRepositoryProvider.overrideWithValue(repo),
        ],
      );
      addTearDown(container.dispose);
      final controller = container.read(progressOutboxControllerProvider);

      await store.enqueueProgress(_push(lastPage: 3, timeSpent: 10));
      final flushA = controller.flush();
      await firstPostStarted.future;
      // The reader settles on another chapter while the POST is out — the
      // running flush read the table too early to see it.
      await store.enqueueProgress(
        const ProgressPush(
          sourceId: 'asura',
          seriesKey: 'solo-leveling',
          chapterKey: '2',
          lastPage: 4,
          pageCount: 20,
          timeSpentSeconds: 20,
        ),
      );
      final flushB = controller.flush();
      releaseFirstPost.complete();
      await Future.wait([flushA, flushB]);

      expect(await store.pendingProgressOutbox(), isEmpty);
      expect(
        sent.expand((b) => b).map((p) => p.chapterKey),
        containsAll(<String>['1', '2']),
      );
    });
  });

  group('OUTBOX-2 bookmark sync across a profile switch', () {
    test('a listing answered after the switch is discarded, not merged into '
        'the outgoing profile', () async {
      SharedPreferences.setMockInitialValues({});
      final prefs = await SharedPreferences.getInstance();

      final repo = _Repo();
      final listRequested = Completer<void>();
      final releaseList = Completer<List<Bookmark>>();
      when(
        () => repo.listBookmarks(
          sourceId: any(named: 'sourceId'),
          seriesKey: any(named: 'seriesKey'),
          since: any(named: 'since'),
          includeDeleted: any(named: 'includeDeleted'),
          limit: any(named: 'limit'),
        ),
      ).thenAnswer((_) async {
        listRequested.complete();
        return Ok(await releaseList.future);
      });

      final container = ProviderContainer(
        overrides: [
          sharedPrefsProvider.overrideWithValue(prefs),
          authenticatedAuthOverride(), // user 1
          activeProfileOverride(), // profile 1 → scope u1p1
          downloadsDatabaseProvider
              .overrideWith((ref) => harness.openDatabase()),
          blobStoreProvider.overrideWith((ref) => harness.openBlobStore()),
          readerRepositoryProvider.overrideWithValue(repo),
        ],
      );
      addTearDown(container.dispose);

      final controllerP1 = container.read(bookmarkOutboxControllerProvider);
      expect(controllerP1.store!.scopeId, 'u1p1');

      // Launch/resume: DownloadsLifecycleGate fires sync() unawaited.
      final inFlight = controllerP1.sync();
      await listRequested.future;

      // …and the switcher chip is tapped while the GET is in flight. The
      // request carries the profile header it was built with, so the answer
      // belongs to whichever profile the server saw — never to this store.
      await container.read(activeProfileProvider.notifier).select(
            Profile(
              id: 2,
              name: 'Kid',
              avatarKey: null,
              mood: Mood.neutral,
              sortOrder: 1,
              matureContentEnabled: false,
              createdAt: DateTime.utc(2026),
            ),
          );
      await container.pump();
      expect(container.read(downloadsStoreProvider)!.scopeId, 'u1p2');

      releaseList.complete([
        Bookmark(
          id: 77,
          clientId: 'kid-bookmark',
          sourceId: 'asura',
          seriesKey: 'solo-leveling',
          chapterKey: '1',
          createdAt: DateTime.utc(2026, 9, 4),
          updatedAt: DateTime.utc(2026, 9, 4),
        ),
      ]);
      expect(await inFlight, isFalse);

      final p1Rows = await harness.storeFor('u1p1').listBookmarks();
      expect(
        p1Rows.map((b) => b.clientId),
        isNot(contains('kid-bookmark')),
        reason: 'the outgoing profile absorbed the incoming one\'s bookmarks',
      );
      final p2Rows = await harness.storeFor('u1p2').listBookmarks();
      expect(
        p2Rows,
        isEmpty,
        reason: 'nor may it be written into the new scope — the old '
            'controller cannot know which profile the answer describes',
      );
    });
  });

  group('OUTBOX-4 offline outbox growth', () {
    test('an offline evening neither re-reads the outbox per save nor lets it '
        'grow without bound, and loses no reading time', () async {
      var offline = true;
      final repo = _Repo();
      final sent = <List<ProgressPush>>[];
      when(() => repo.saveProgressBatch(any())).thenAnswer((inv) async {
        if (offline) return const Err(NetworkError(message: 'offline'));
        sent.add(inv.positionalArguments.first as List<ProgressPush>);
        return const Ok((saved: 1, advanced: 1));
      });

      final store = _CountingStore(harness.storeFor('u1p1'));
      final container = ProviderContainer(
        overrides: [
          downloadsStoreProvider.overrideWithValue(store),
          readerRepositoryProvider.overrideWithValue(repo),
        ],
      );
      addTearDown(container.dispose);
      final controller = container.read(progressOutboxControllerProvider);

      // 400 page settles on one chapter, all offline: each is one save().
      for (var i = 1; i <= 400; i++) {
        await controller.save(_push(lastPage: (i % 20) + 1, timeSpent: 1));
      }

      expect(
        store.outboxReads,
        lessThan(20),
        reason: '${store.outboxReads} full outbox reads for 400 saves — the '
            'per-save cost still grows with what is already queued',
      );
      final rows = await store.pendingProgressOutbox();
      expect(
        rows.length,
        lessThanOrEqualTo(kProgressBatchMaxItems),
        reason: '${rows.length} rows queued for a single chapter — unbounded',
      );

      // Back online: nothing the evening recorded may have been dropped.
      offline = false;
      await controller.flush();

      expect(await store.pendingProgressOutbox(), isEmpty);
      final delivered = sent.expand((b) => b).toList();
      expect(delivered.map((p) => p.chapterKey).toSet(), {'1'});
      expect(
        delivered.fold<int>(0, (a, p) => a + p.timeSpentSeconds),
        400,
        reason: 'the 400 one-second deltas must arrive summed, not thinned',
      );
      expect(
        delivered.map((p) => p.lastPage).reduce((a, b) => a > b ? a : b),
        20,
      );
    });

    test('an outbox spanning more chapters than the ceiling keeps the newest',
        () async {
      final repo = _Repo();
      when(() => repo.saveProgressBatch(any())).thenAnswer(
        (_) async => const Err(NetworkError(message: 'offline')),
      );

      final store = harness.storeFor('u1p1');
      final container = ProviderContainer(
        overrides: [
          downloadsStoreProvider.overrideWithValue(store),
          readerRepositoryProvider.overrideWithValue(repo),
        ],
      );
      addTearDown(container.dispose);
      final controller = container.read(progressOutboxControllerProvider);

      // Folding bounds the rows one chapter can leave behind; this is the
      // other axis — a different chapter every time, so nothing folds.
      const saves = kProgressOutboxMaxGroups + 101;
      for (var i = 1; i <= saves; i++) {
        await controller.save(
          ProgressPush(
            sourceId: 'asura',
            seriesKey: 'solo-leveling',
            chapterKey: 'c$i',
            lastPage: 3,
            pageCount: 20,
            timeSpentSeconds: 1,
          ),
        );
      }

      final queued = await store.pendingProgressOutbox();
      expect(queued.length, lessThanOrEqualTo(kProgressOutboxMaxGroups));
      final chapters = queued.map((row) => row.$2.chapterKey).toSet();
      expect(chapters, contains('c$saves'));
      expect(chapters, isNot(contains('c1')));
    });
  });

  group('OUTBOX-3 an unsendable row wedging the outbox', () {
    ProgressPush chapter(String key) => ProgressPush(
          sourceId: 'asura',
          seriesKey: 'solo-leveling',
          chapterKey: key,
          lastPage: 3,
          pageCount: 20,
          timeSpentSeconds: 5,
        );

    test('a 422 drops the row the server named and lets the rest through',
        () async {
      final repo = _Repo();
      final sent = <List<ProgressPush>>[];
      when(() => repo.saveProgressBatch(any())).thenAnswer((inv) async {
        final batch = inv.positionalArguments.first as List<ProgressPush>;
        sent.add(batch);
        final bad = batch.indexWhere((p) => p.chapterKey == 'poison');
        if (bad < 0) return const Ok((saved: 1, advanced: 1));
        // The batch is validated as a unit: nothing in it merged, and the
        // offending item is named by its position in the posted array.
        return Err(
          ApiError(
            statusCode: 422,
            code: 'validation_error',
            message: 'Invalid request.',
            details: [
              {
                'loc': ['body', bad, 'chapter_key'],
                'msg': 'String should have at most 512 characters',
                'type': 'string_too_long',
              },
            ],
          ),
        );
      });

      final store = harness.storeFor('u1p1');
      final container = ProviderContainer(
        overrides: [
          downloadsStoreProvider.overrideWithValue(store),
          readerRepositoryProvider.overrideWithValue(repo),
        ],
      );
      addTearDown(container.dispose);
      final controller = container.read(progressOutboxControllerProvider);

      await store.enqueueProgress(chapter('1'));
      await store.enqueueProgress(chapter('poison'));
      await store.enqueueProgress(chapter('3'));

      // Two triggers, as the app has: the save's own attempt and the next
      // lifecycle event. No number of them may keep re-posting the bad row.
      await controller.flush();
      await controller.flush();

      expect(
        sent.expand((b) => b).where((p) => p.chapterKey == 'poison').length,
        1,
        reason: 'the row the server can never accept was posted again',
      );
      expect(
        await store.pendingProgressOutbox(),
        isEmpty,
        reason: 'the good rows behind it never left the device',
      );
      expect(
        sent.expand((b) => b).map((p) => p.chapterKey),
        containsAll(<String>['1', '3']),
      );
    });

    test('a refusal that names no row still settles the batch it refused',
        () async {
      final repo = _Repo();
      var posts = 0;
      when(() => repo.saveProgressBatch(any())).thenAnswer((_) async {
        posts++;
        return const Err(
          ApiError(
            statusCode: 422,
            code: 'validation_error',
            message: 'Invalid request.',
          ),
        );
      });

      final store = harness.storeFor('u1p1');
      final container = ProviderContainer(
        overrides: [
          downloadsStoreProvider.overrideWithValue(store),
          readerRepositoryProvider.overrideWithValue(repo),
        ],
      );
      addTearDown(container.dispose);
      final controller = container.read(progressOutboxControllerProvider);

      await store.enqueueProgress(chapter('1'));
      await store.enqueueProgress(chapter('2'));
      await controller.flush();
      await controller.flush();

      expect(await store.pendingProgressOutbox(), isEmpty);
      expect(
        posts,
        1,
        reason: 'a payload the server rejects outright was posted $posts '
            'times — every later flush takes the same refusal',
      );
    });
  });

  group('OUTBOX-2 progress drain across a profile switch', () {
    test('rows read for one profile are never posted under another profile\'s '
        'header', () async {
      final repo = _Repo();
      final posted = <List<ProgressPush>>[];
      when(() => repo.saveProgressBatch(any())).thenAnswer((inv) async {
        posted.add(inv.positionalArguments.first as List<ProgressPush>);
        return const Ok((saved: 1, advanced: 1));
      });

      SharedPreferences.setMockInitialValues({});
      final prefs = await SharedPreferences.getInstance();
      final paused = _PausingStore(harness.storeFor('u1p1'));
      final container = ProviderContainer(
        overrides: [
          sharedPrefsProvider.overrideWithValue(prefs),
          authenticatedAuthOverride(), // user 1
          activeProfileOverride(), // profile 1 -> scope u1p1
          downloadsDatabaseProvider.overrideWith((ref) => harness.openDatabase()),
          blobStoreProvider.overrideWith((ref) => harness.openBlobStore()),
          readerRepositoryProvider.overrideWithValue(repo),
          downloadsStoreProvider.overrideWith((ref) => paused),
        ],
      );
      addTearDown(container.dispose);

      await paused.enqueueProgress(_push(timeSpent: 30));

      final controller = container.read(progressOutboxControllerProvider);
      final inFlight = controller.flush();
      await paused.reading.future;

      // The switcher chip is tapped while the drain holds rows it read for
      // profile 1. The Dio header is mutated in place, so a POST issued from
      // here would be answered for profile 2.
      await container.read(activeProfileProvider.notifier).select(
            Profile(
              id: 2,
              name: 'Kid',
              avatarKey: null,
              mood: Mood.neutral,
              sortOrder: 1,
              matureContentEnabled: false,
              createdAt: DateTime.utc(2026),
            ),
          );
      await container.pump();
      paused.release.complete();
      await inFlight;

      expect(
        posted,
        isEmpty,
        reason: 'profile 1\'s positions were pushed under profile 2\'s header',
      );
      expect(
        (await harness.storeFor('u1p1').pendingProgressOutbox()).length,
        1,
        reason: 'and the row must stay queued for the profile it belongs to',
      );
    });
  });

}
