import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/core/error/app_error.dart';
import 'package:manhwamaniacs/core/utils/result.dart';
import 'package:manhwamaniacs/features/downloads/providers/bookmark_outbox_provider.dart';
import 'package:manhwamaniacs/features/downloads/providers/downloads_scope.dart';
import 'package:manhwamaniacs/features/downloads/store/bookmarks_dao.dart';
import 'package:manhwamaniacs/features/downloads/store/downloads_store.dart';
import 'package:manhwamaniacs/features/reader/models/bookmark.dart';
import 'package:manhwamaniacs/features/reader/models/chapter_manifest.dart';
import 'package:manhwamaniacs/features/reader/models/reading_progress.dart';
import 'package:manhwamaniacs/features/reader/repositories/reader_repository.dart';
import 'package:manhwamaniacs/shared/providers/repository_providers.dart';

import '../../support/downloads_test_support.dart';

const _chapter =
    (sourceId: 'asurascans', seriesKey: 'solo-leveling', chapterKey: '132');

class _ScriptedReaderRepository implements ReaderRepository {
  /// What `GET /reader/bookmarks` answers — assigned per test, so a pull can
  /// be made to carry another device's news.
  List<Bookmark> remote = const [];
  final List<List<BookmarkOp>> batches = [];
  bool failPush = false;

  /// Server ids handed back per client id, or 0 to hand none back (a delete
  /// of an id the server never saw echoes no body).
  int nextServerId = 1;

  @override
  Future<Result<BookmarkSyncResult>> syncBookmarks(List<BookmarkOp> ops) async {
    if (failPush) return const Err(NetworkError(message: 'offline'));
    batches.add(ops);
    return Ok(
      BookmarkSyncResult(
        received: ops.length,
        created: ops.where((o) => !o.isDelete).length,
        updated: 0,
        tombstoned: ops.where((o) => o.isDelete).length,
        rejected: 0,
        serverIds: {
          for (final op in ops)
            if (!op.isDelete) op.bookmark.clientId: nextServerId++,
        },
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
  }) async =>
      Ok(remote);

  @override
  Future<Result<void>> deleteBookmark(int bookmarkId) =>
      throw UnimplementedError();

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

void main() {
  initSqfliteFfiForTests();

  late TestDownloadsHarness harness;
  late DownloadsStore store;

  setUp(() async {
    harness = await TestDownloadsHarness.create();
    store = harness.storeFor('u1p1');
    // Open it here rather than lazily: a test that never touches the store
    // (the no-scope cases) would otherwise leave `openDatabase` in flight
    // when tearDown deletes the temp directory, and the failure surfaces as
    // a disk I/O error blamed on whichever test happens to be running.
    await store.listBookmarks();
  });

  tearDown(() async => harness.dispose());

  BookmarkOutboxController controllerFor(
    ReaderRepository repo, {
    DownloadsStore? withStore,
    bool noScope = false,
  }) {
    final container = ProviderContainer(
      overrides: [
        downloadsStoreProvider.overrideWithValue(
          noScope ? null : (withStore ?? store),
        ),
        readerRepositoryProvider.overrideWithValue(repo),
      ],
    );
    addTearDown(container.dispose);
    return container.read(bookmarkOutboxControllerProvider);
  }

  Future<Bookmark?> bookmarkAt(
    BookmarkOutboxController controller, {
    int index = 7,
    double fraction = 0.62,
    int total = 11,
    BookmarkMedia media = BookmarkMedia.manga,
    String? snippet,
  }) =>
      controller.create(
        id: _chapter,
        media: media,
        anchorIndex: index,
        anchorFraction: fraction,
        anchorTotal: total,
        chapterNumber: 14,
        snippet: snippet,
      );

  group('create', () {
    test('stores the exact position and pushes it', () async {
      final repo = _ScriptedReaderRepository();
      final controller = controllerFor(repo);

      final saved = await bookmarkAt(controller);

      expect(saved, isNotNull);
      expect(saved!.anchorIndex, 7);
      expect(saved.anchorFraction, closeTo(0.62, 1e-9));
      expect(saved.anchorTotal, 11);
      expect(repo.batches.single.single.op, kBookmarkOpUpsert);
      // Accepted, so nothing is left queued.
      expect(await store.pendingBookmarkOutbox(), isEmpty);
    });

    test('bookmarking offline is an ordinary success, and stays queued',
        () async {
      final repo = _ScriptedReaderRepository()..failPush = true;
      final controller = controllerFor(repo);

      final saved = await bookmarkAt(controller);

      // This is the whole feature: the reader gets a bookmark, on a plane.
      expect(saved, isNotNull);
      expect((await store.listBookmarks()).single.clientId, saved!.clientId);
      expect(await store.pendingBookmarkOutbox(), hasLength(1));
    });

    test('the server id is adopted once the flush comes back', () async {
      final repo = _ScriptedReaderRepository()..failPush = true;
      final controller = controllerFor(repo);
      final saved = await bookmarkAt(controller);
      expect(saved!.id, isNull);

      repo.failPush = false;
      await controller.flush();

      expect((await store.getBookmark(saved.clientId))!.id, 1);
    });

    test('two bookmarks in one chapter both survive — the id is the client\'s '
        'uuid, not the position', () async {
      final controller = controllerFor(_ScriptedReaderRepository());

      final a = await bookmarkAt(controller, index: 3);
      final b = await bookmarkAt(controller, index: 9);

      expect(a!.clientId, isNot(b!.clientId));
      expect(await store.listBookmarks(), hasLength(2));
    });

    test('a novel bookmark keeps its snippet on the device', () async {
      final controller = controllerFor(_ScriptedReaderRepository());

      await bookmarkAt(
        controller,
        media: BookmarkMedia.novel,
        index: 340,
        total: 800,
        snippet: '…the mana core pulsed once.',
      );

      final stored = (await store.listBookmarks()).single;
      expect(stored.mediaType, BookmarkMedia.novel);
      // Cached at capture, because deriving it later needs the chapter's
      // text — which is exactly what a phone with no signal does not have.
      expect(stored.snippet, '…the mana core pulsed once.');
    });

    test('with no active scope it stores nothing rather than guessing one',
        () async {
      final controller = controllerFor(
        _ScriptedReaderRepository(),
        noScope: true,
      );

      expect(await bookmarkAt(controller), isNull);
      expect(await store.listBookmarks(), isEmpty);
    });
  });

  group('remove', () {
    test('a delete made offline reaches the server on the next flush',
        () async {
      final repo = _ScriptedReaderRepository()..failPush = true;
      final controller = controllerFor(repo);
      final saved = await bookmarkAt(controller);

      await controller.remove(saved!.clientId);
      expect(await store.listBookmarks(), isEmpty);

      repo.failPush = false;
      await controller.flush();

      final ops = repo.batches.expand((b) => b).toList();
      // In order: the create the server never saw, then the delete. Reversed,
      // the delete would no-op and the create would land as a live bookmark
      // both sides believe is gone.
      expect(ops.map((o) => o.op), [kBookmarkOpUpsert, kBookmarkOpDelete]);
      expect(await store.pendingBookmarkOutbox(), isEmpty);
    });

    test('removing an id this scope never held pushes nothing', () async {
      final repo = _ScriptedReaderRepository();
      final controller = controllerFor(repo);

      expect(await controller.remove('never-seen'), isFalse);
      expect(repo.batches, isEmpty);
    });
  });

  group('flush', () {
    test('a failure leaves every queued op exactly where it was', () async {
      final repo = _ScriptedReaderRepository()..failPush = true;
      final controller = controllerFor(repo);
      await bookmarkAt(controller);
      await bookmarkAt(controller, index: 2);

      await controller.flush();

      expect(await store.pendingBookmarkOutbox(), hasLength(2));
    });

    test('more ops than one batch allows are sent in several, in order',
        () async {
      // Queue without flushing, so the whole backlog is there at once.
      final repo = _ScriptedReaderRepository()..failPush = true;
      final controller = controllerFor(repo);
      for (var i = 0; i < kBookmarkBatchMaxItems + 5; i++) {
        await bookmarkAt(controller, index: i + 1);
      }
      expect(
        await store.pendingBookmarkOutbox(),
        hasLength(kBookmarkBatchMaxItems + 5),
      );

      repo.failPush = false;
      await controller.flush();

      expect(repo.batches.map((b) => b.length), [kBookmarkBatchMaxItems, 5]);
      expect(await store.pendingBookmarkOutbox(), isEmpty);
    });

    test('nothing queued means no request at all', () async {
      final repo = _ScriptedReaderRepository();
      await controllerFor(repo).flush();
      expect(repo.batches, isEmpty);
    });

    test('with no scope it is a safe no-op', () async {
      final repo = _ScriptedReaderRepository();
      await controllerFor(repo, noScope: true).flush();
      expect(repo.batches, isEmpty);
    });
  });

  group('sync', () {
    test('pushes first, then folds the server listing in', () async {
      final repo = _ScriptedReaderRepository();
      final controller = controllerFor(repo);
      await bookmarkAt(controller);

      repo.remote = [
        Bookmark(
          id: 9,
          clientId: 'from-the-web',
          sourceId: 'asurascans',
          seriesKey: 'solo-leveling',
          chapterKey: '133',
          anchorIndex: 2,
          anchorTotal: 8,
          createdAt: DateTime.utc(2026, 9, 5),
          updatedAt: DateTime.utc(2026, 9, 5),
        ),
      ];

      expect(await controller.sync(), isTrue);
      expect(
        (await store.listBookmarks()).map((b) => b.clientId),
        contains('from-the-web'),
      );
    });

    test('a pull with nothing new reports no change, so no needless re-read',
        () async {
      final repo = _ScriptedReaderRepository();
      final controller = controllerFor(repo);

      expect(await controller.sync(), isFalse);
    });

    test('an unreachable server never throws and changes nothing', () async {
      final repo = _ScriptedReaderRepository()..failPush = true;
      final controller = controllerFor(repo);
      await bookmarkAt(controller);

      expect(await controller.sync(), isFalse);
      expect(await store.listBookmarks(), hasLength(1));
      expect(await store.pendingBookmarkOutbox(), hasLength(1));
    });
  });

  group('cross-profile', () {
    test('a flush for one profile never drains another profile\'s outbox',
        () async {
      final other = harness.storeFor('u1p2');
      final repo = _ScriptedReaderRepository()..failPush = true;

      await controllerFor(repo, withStore: other).create(
        id: _chapter,
        media: BookmarkMedia.manga,
        anchorIndex: 1,
        anchorFraction: 0,
        anchorTotal: 5,
      );
      await bookmarkAt(controllerFor(repo));

      repo.failPush = false;
      await controllerFor(repo).flush();

      expect(await store.pendingBookmarkOutbox(), isEmpty);
      expect(await other.pendingBookmarkOutbox(), hasLength(1));
      expect(await other.listBookmarks(), hasLength(1));
      expect(await store.listBookmarks(), hasLength(1));
    });
  });
}
