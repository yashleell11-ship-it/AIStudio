import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/core/error/app_error.dart';
import 'package:manhwamaniacs/core/utils/result.dart';
import 'package:manhwamaniacs/features/downloads/providers/downloads_scope.dart';
import 'package:manhwamaniacs/features/downloads/store/bookmarks_dao.dart';
import 'package:manhwamaniacs/features/downloads/store/downloads_store.dart';
import 'package:manhwamaniacs/features/library/providers/bookmarks_provider.dart';
import 'package:manhwamaniacs/features/reader/models/bookmark.dart';
import 'package:manhwamaniacs/features/reader/models/chapter_manifest.dart';
import 'package:manhwamaniacs/features/reader/models/reading_progress.dart';
import 'package:manhwamaniacs/features/reader/repositories/reader_repository.dart';
import 'package:manhwamaniacs/shared/providers/repository_providers.dart';

import '../../support/downloads_test_support.dart';

/// A reader repository that records what the device pushed and can be held
/// mid-flush via a [Completer], so a test can observe `actionPending` while a
/// delete is still in the air.
class _FakeReaderRepository implements ReaderRepository {
  _FakeReaderRepository({this.remote = const []});

  List<Bookmark> remote;
  final List<BookmarkOp> pushed = [];
  Completer<void>? pushGate;
  bool failPush = false;
  int listCallCount = 0;

  @override
  Future<Result<BookmarkSyncResult>> syncBookmarks(List<BookmarkOp> ops) async {
    if (pushGate != null) await pushGate!.future;
    if (failPush) return const Err(NetworkError(message: 'offline'));
    pushed.addAll(ops);
    return Ok(
      BookmarkSyncResult(
        received: ops.length,
        created: ops.length,
        updated: 0,
        tombstoned: 0,
        rejected: 0,
        serverIds: {for (final op in ops) op.bookmark.clientId: 77},
      ),
    );
  }

  @override
  Future<Result<List<Bookmark>>> listBookmarks({
    String? sourceId,
    String? seriesKey,
    DateTime? since,
    bool includeDeleted = false,
    int? limit,
  }) async {
    listCallCount++;
    return Ok(remote);
  }

  @override
  Future<Result<void>> deleteBookmark(int bookmarkId) async => const Ok(null);

  @override
  Future<Result<ChapterManifest>> manifest({
    required String sourceId,
    required String seriesKey,
    required String chapterKey,
  }) =>
      throw UnimplementedError();

  @override
  Future<Result<ReadingProgress>> saveProgress(ProgressPush push) =>
      throw UnimplementedError();

  @override
  Future<Result<({int saved, int advanced})>> saveProgressBatch(
    List<ProgressPush> pushes,
  ) =>
      throw UnimplementedError();

  @override
  Future<Result<List<ReadingProgress>>> seriesProgress({
    required String sourceId,
    required String seriesKey,
  }) =>
      throw UnimplementedError();
}

Bookmark _bookmark({
  String clientId = 'c1',
  String chapterKey = '14',
  int index = 7,
  double fraction = 0.62,
  int total = 11,
  DateTime? updatedAt,
}) =>
    Bookmark(
      clientId: clientId,
      sourceId: 'asurascans',
      seriesKey: 'solo-leveling',
      chapterKey: chapterKey,
      chapterNumber: 14,
      anchorIndex: index,
      anchorFraction: fraction,
      anchorTotal: total,
      createdAt: DateTime.utc(2026, 9, 5),
      updatedAt: updatedAt ?? DateTime.utc(2026, 9, 5),
    );

void main() {
  initSqfliteFfiForTests();

  late TestDownloadsHarness harness;
  late DownloadsStore store;

  setUp(() async {
    harness = await TestDownloadsHarness.create();
    store = harness.storeFor('u1p1');
  });

  tearDown(() async => harness.dispose());

  ProviderContainer buildContainer(_FakeReaderRepository repo) {
    final container = ProviderContainer(
      overrides: [
        downloadsStoreProvider.overrideWithValue(store),
        readerRepositoryProvider.overrideWithValue(repo),
      ],
    );
    addTearDown(container.dispose);
    // Hold the autoDispose provider alive the way a mounted screen's
    // `ref.watch` does — without a listener it is torn down between reads and
    // every `container.read` rebuilds it back into AsyncLoading.
    container.listen(bookmarksProvider, (_, __) {}, fireImmediately: true);
    return container;
  }

  group('BookmarksNotifier reads the device first', () {
    test('lists bookmarks off the device with the network refusing every call',
        () async {
      await store.saveBookmark(_bookmark());
      await store.saveBookmark(_bookmark(clientId: 'c2', chapterKey: '15'));
      final repo = _FakeReaderRepository()..failPush = true;
      final container = buildContainer(repo);

      final data = await container.read(bookmarksProvider.future);

      expect(data.bookmarks.map((b) => b.clientId), containsAll(['c1', 'c2']));
      expect(data.actionPending, isFalse);
    });

    test('a tombstoned bookmark is not listed', () async {
      await store.saveBookmark(_bookmark());
      await store.tombstoneBookmark('c1');
      final container = buildContainer(_FakeReaderRepository());

      final data = await container.read(bookmarksProvider.future);

      expect(data.bookmarks, isEmpty);
    });

    test('the position survives the round trip through the device table',
        () async {
      await store.saveBookmark(_bookmark());
      final container = buildContainer(_FakeReaderRepository());

      final stored = (await container.read(bookmarksProvider.future))
          .bookmarks
          .single;

      expect(stored.anchorIndex, 7);
      expect(stored.anchorFraction, closeTo(0.62, 1e-9));
      expect(stored.anchorTotal, 11);
      // (7 - 1 + 0.62) / 11 -> 0.6018, the same arithmetic the server does.
      expect(stored.positionFraction, closeTo(0.6018, 1e-9));
      expect(stored.positionPercent, 60);
    });
  });

  group('BookmarksNotifier delete', () {
    test('sets actionPending immediately, then clears it and drops the row',
        () async {
      await store.saveBookmark(_bookmark());
      final repo = _FakeReaderRepository()..pushGate = Completer<void>();
      final container = buildContainer(repo);

      await container.read(bookmarksProvider.future);
      final notifier = container.read(bookmarksProvider.notifier);
      expect(
        container.read(bookmarksProvider).valueOrNull?.actionPending,
        isFalse,
      );

      final pending = notifier.deleteBookmark(_bookmark());
      expect(
        container.read(bookmarksProvider).valueOrNull?.actionPending,
        isTrue,
      );

      repo.pushGate!.complete();
      await pending;

      final state = container.read(bookmarksProvider).valueOrNull;
      expect(state?.actionPending, isFalse);
      expect(state?.bookmarks, isEmpty);
    });

    test('deleting with the server unreachable still removes it locally and '
        'leaves the delete queued', () async {
      await store.saveBookmark(_bookmark());
      final repo = _FakeReaderRepository()..failPush = true;
      final container = buildContainer(repo);
      await container.read(bookmarksProvider.future);

      final error =
          await container.read(bookmarksProvider.notifier).deleteBookmark(
                _bookmark(),
              );

      expect(error, isNull);
      expect(container.read(bookmarksProvider).valueOrNull?.bookmarks, isEmpty);
      final queued = await store.pendingBookmarkOutbox();
      expect(queued.last.$2.op, kBookmarkOpDelete);
      expect(queued.last.$2.bookmark.clientId, 'c1');
    });
  });

  group('BookmarksNotifier refresh', () {
    test('learns about a delete made on another device', () async {
      await store.saveBookmark(_bookmark());
      final repo = _FakeReaderRepository(
        remote: [
          _bookmark(updatedAt: DateTime.utc(2026, 9, 6)).copyWith(
            id: 3,
            deleted: true,
            deletedAt: DateTime.utc(2026, 9, 6),
          ),
        ],
      );
      final container = buildContainer(repo);
      expect(
        (await container.read(bookmarksProvider.future)).bookmarks,
        hasLength(1),
      );

      await container.read(bookmarksProvider.notifier).refresh();

      expect(container.read(bookmarksProvider).valueOrNull?.bookmarks, isEmpty);
    });

    test('a failed pull leaves the device list exactly as it was', () async {
      await store.saveBookmark(_bookmark());
      final repo = _FakeReaderRepository()..failPush = true;
      final container = buildContainer(repo);

      await container.read(bookmarksProvider.notifier).refresh();

      expect(
        container.read(bookmarksProvider).valueOrNull?.bookmarks,
        hasLength(1),
      );
    });
  });
}
