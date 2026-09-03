import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/core/error/app_error.dart';
import 'package:manhwamaniacs/core/utils/result.dart';
import 'package:manhwamaniacs/features/library/providers/bookmarks_provider.dart';
import 'package:manhwamaniacs/features/reader/models/bookmark.dart';
import 'package:manhwamaniacs/features/reader/models/chapter_manifest.dart';
import 'package:manhwamaniacs/features/reader/models/reading_progress.dart';
import 'package:manhwamaniacs/features/reader/repositories/reader_repository.dart';
import 'package:manhwamaniacs/shared/providers/repository_providers.dart';

/// Fake whose [deleteBookmark] can be held pending via a [Completer], so
/// tests can observe the notifier's `actionPending` state mid-flight --
/// mirroring the pattern in updates_provider_test.dart for
/// UpdatesNotifier.unfollow.
class _FakeReaderRepository implements ReaderRepository {
  _FakeReaderRepository({this.bookmarks = const []});

  List<Bookmark> bookmarks;
  Completer<void>? deleteGate;
  int deleteCallCount = 0;
  bool failDelete = false;

  @override
  Future<Result<List<Bookmark>>> listBookmarks({
    String? sourceId,
    String? seriesKey,
  }) async =>
      Ok(bookmarks);

  @override
  Future<Result<void>> deleteBookmark(int bookmarkId) async {
    deleteCallCount++;
    if (deleteGate != null) await deleteGate!.future;
    if (failDelete) {
      return const Err(NetworkError(message: 'boom'));
    }
    bookmarks = bookmarks.where((b) => b.id != bookmarkId).toList();
    return const Ok(null);
  }

  @override
  Future<Result<Bookmark>> addBookmark({
    required String sourceId,
    required String seriesKey,
    required String chapterKey,
    required int page,
    String? note,
  }) =>
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

Bookmark _bookmark({int id = 1}) => Bookmark(
      id: id,
      sourceId: 'asurascans',
      seriesKey: 'solo-leveling',
      chapterKey: '1',
      page: 3,
      createdAt: DateTime(2026),
    );

void main() {
  group('BookmarksNotifier', () {
    test('lists bookmarks from the repository', () async {
      final repo = _FakeReaderRepository(bookmarks: [_bookmark(), _bookmark(id: 2)]);
      final container = ProviderContainer(
        overrides: [readerRepositoryProvider.overrideWithValue(repo)],
      );
      addTearDown(container.dispose);

      final data = await container.read(bookmarksProvider.future);

      expect(data.bookmarks.length, 2);
      expect(data.actionPending, isFalse);
    });

    test(
        'deleteBookmark sets actionPending immediately, then clears it and '
        'refreshes the list once the delete resolves', () async {
      final repo = _FakeReaderRepository(bookmarks: [_bookmark()])
        ..deleteGate = Completer<void>();
      final container = ProviderContainer(
        overrides: [readerRepositoryProvider.overrideWithValue(repo)],
      );
      addTearDown(container.dispose);

      await container.read(bookmarksProvider.future);
      final notifier = container.read(bookmarksProvider.notifier);

      expect(container.read(bookmarksProvider).valueOrNull?.actionPending, isFalse);

      final pending = notifier.deleteBookmark(1);
      expect(container.read(bookmarksProvider).valueOrNull?.actionPending, isTrue);

      repo.deleteGate!.complete();
      await pending;

      final state = container.read(bookmarksProvider).valueOrNull;
      expect(state?.actionPending, isFalse);
      expect(state?.bookmarks, isEmpty);
      expect(repo.deleteCallCount, 1);
    });

    test('clears actionPending on failure without leaving the button stuck busy', () async {
      final repo = _FakeReaderRepository(bookmarks: [_bookmark()])..failDelete = true;
      final container = ProviderContainer(
        overrides: [readerRepositoryProvider.overrideWithValue(repo)],
      );
      addTearDown(container.dispose);

      await container.read(bookmarksProvider.future);
      final notifier = container.read(bookmarksProvider.notifier);

      final error = await notifier.deleteBookmark(1);

      expect(error, isNotNull);
      expect(container.read(bookmarksProvider).valueOrNull?.actionPending, isFalse);
      // The optimistic delete only commits after a successful refresh.
      expect(container.read(bookmarksProvider).valueOrNull?.bookmarks.length, 1);
    });
  });
}
