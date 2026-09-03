import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/core/error/app_error.dart';
import 'package:manhwamaniacs/core/utils/result.dart';
import 'package:manhwamaniacs/features/downloads/providers/downloads_scope.dart';
import 'package:manhwamaniacs/features/downloads/providers/progress_outbox_provider.dart';
import 'package:manhwamaniacs/features/reader/models/reading_progress.dart';
import 'package:manhwamaniacs/features/reader/repositories/reader_repository.dart';
import 'package:manhwamaniacs/shared/providers/repository_providers.dart';
import 'package:mocktail/mocktail.dart';

import '../../support/downloads_test_support.dart';

class _ScriptedReaderRepository extends Mock implements ReaderRepository {}

ProgressPush _push({String chapterKey = '1', int lastPage = 5}) => ProgressPush(
      sourceId: 'asura',
      seriesKey: 'solo-leveling',
      chapterKey: chapterKey,
      chapterNumber: 1,
      lastPage: lastPage,
      pageCount: 20,
    );

void main() {
  initSqfliteFfiForTests();
  setUpAll(() {
    registerFallbackValue(<ProgressPush>[]);
  });

  late TestDownloadsHarness harness;

  setUp(() async {
    harness = await TestDownloadsHarness.create();
  });

  tearDown(() async {
    await harness.dispose();
  });

  group('DownloadsStore progress outbox (store level)', () {
    test('enqueue then pending round-trips the exact push', () async {
      final store = harness.storeFor('u1p1');
      await store.enqueueProgress(_push(lastPage: 7));

      final pending = await store.pendingProgressOutbox();
      expect(pending, hasLength(1));
      final push = pending.single.$2;
      expect(push.sourceId, 'asura');
      expect(push.seriesKey, 'solo-leveling');
      expect(push.chapterKey, '1');
      expect(push.lastPage, 7);
      expect(push.pageCount, 20);
    });

    test('pending outbox entries are scope-isolated', () async {
      final storeA = harness.storeFor('u1p1');
      final storeB = harness.storeFor('u1p2');
      await storeA.enqueueProgress(_push());

      expect(await storeA.pendingProgressOutbox(), hasLength(1));
      expect(await storeB.pendingProgressOutbox(), isEmpty);
    });

    test('clearProgressOutbox removes only the given ids, scoped', () async {
      final storeA = harness.storeFor('u1p1');
      final storeB = harness.storeFor('u1p2');
      await storeA.enqueueProgress(_push());
      await storeA.enqueueProgress(_push(chapterKey: '2'));
      await storeB.enqueueProgress(_push());

      final pendingA = await storeA.pendingProgressOutbox();
      await storeA.clearProgressOutbox([pendingA.first.$1]);

      final remainingA = await storeA.pendingProgressOutbox();
      expect(remainingA, hasLength(1));
      expect(remainingA.single.$2.chapterKey, pendingA.last.$2.chapterKey);
      // B's row survives A's clear untouched — clearing can't cross scopes
      // even if (by coincidence) the two scopes' outbox ids ever collided.
      expect(await storeB.pendingProgressOutbox(), hasLength(1));
    });

    test('pending entries are returned oldest-first', () async {
      final store = harness.storeFor('u1p1');
      await store.enqueueProgress(_push(chapterKey: 'first'));
      await store.enqueueProgress(_push(chapterKey: 'second'));
      await store.enqueueProgress(_push(chapterKey: 'third'));

      final pending = await store.pendingProgressOutbox();
      expect(pending.map((e) => e.$2.chapterKey), ['first', 'second', 'third']);
    });
  });

  group('ProgressOutboxController.save/flush', () {
    ProviderContainer buildContainer(ReaderRepository repo) {
      final container = ProviderContainer(
        overrides: [
          downloadsStoreProvider.overrideWithValue(harness.storeFor('u1p1')),
          readerRepositoryProvider.overrideWithValue(repo),
        ],
      );
      addTearDown(container.dispose);
      return container;
    }

    test('save() writes locally then flushes immediately on success',
        () async {
      final repo = _ScriptedReaderRepository();
      when(() => repo.saveProgressBatch(any()))
          .thenAnswer((_) async => const Ok((saved: 1, advanced: 1)));

      final container = buildContainer(repo);
      await container.read(progressOutboxControllerProvider).save(_push());

      final store = harness.storeFor('u1p1');
      expect(await store.pendingProgressOutbox(), isEmpty);
      verify(() => repo.saveProgressBatch(any())).called(1);
    });

    test('a failed flush leaves the write queued — nothing is lost', () async {
      final repo = _ScriptedReaderRepository();
      when(() => repo.saveProgressBatch(any())).thenAnswer(
        (_) async => const Err(NetworkError(message: 'offline')),
      );

      final container = buildContainer(repo);
      // save() must not throw even though the network call fails.
      await container.read(progressOutboxControllerProvider).save(_push(lastPage: 12));

      final store = harness.storeFor('u1p1');
      final pending = await store.pendingProgressOutbox();
      expect(pending, hasLength(1));
      expect(pending.single.$2.lastPage, 12);
    });

    test('replaying a flush after a transient failure eventually clears the '
        'outbox — a retry never loses or duplicates the pending push',
        () async {
      var shouldFail = true;
      final repo = _ScriptedReaderRepository();
      when(() => repo.saveProgressBatch(any())).thenAnswer((invocation) async {
        if (shouldFail) return const Err(NetworkError(message: 'offline'));
        return const Ok((saved: 1, advanced: 1));
      });

      final container = buildContainer(repo);
      final controller = container.read(progressOutboxControllerProvider);

      await controller.save(_push(lastPage: 9));
      final store = harness.storeFor('u1p1');
      expect(await store.pendingProgressOutbox(), hasLength(1));

      // Connectivity regained — the lifecycle gate's next flush trigger.
      shouldFail = false;
      await controller.flush();

      expect(await store.pendingProgressOutbox(), isEmpty);
      // Exactly the same push (still lastPage: 9) was the one that finally
      // went out — nothing was silently dropped or altered by the retry.
      final sentPushes =
          verify(() => repo.saveProgressBatch(captureAny())).captured;
      final lastSentBatch = sentPushes.last as List<ProgressPush>;
      expect(lastSentBatch.single.lastPage, 9);
    });

    test('flush() with nothing pending never calls the repository', () async {
      final repo = _ScriptedReaderRepository();
      final container = buildContainer(repo);

      await container.read(progressOutboxControllerProvider).flush();

      verifyNever(() => repo.saveProgressBatch(any()));
    });

    test('save() with no active scope is a safe no-op', () async {
      final repo = _ScriptedReaderRepository();
      final container = ProviderContainer(
        overrides: [
          downloadsStoreProvider.overrideWithValue(null),
          readerRepositoryProvider.overrideWithValue(repo),
        ],
      );
      addTearDown(container.dispose);

      await container.read(progressOutboxControllerProvider).save(_push());

      verifyNever(() => repo.saveProgressBatch(any()));
    });
  });
}
