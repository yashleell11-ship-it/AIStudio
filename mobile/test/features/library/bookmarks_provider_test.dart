import 'dart:async';

import 'package:aistudio_mobile/core/error/app_error.dart';
import 'package:aistudio_mobile/core/utils/pagination.dart';
import 'package:aistudio_mobile/core/utils/result.dart';
import 'package:aistudio_mobile/features/library/models/chapter.dart';
import 'package:aistudio_mobile/features/library/models/collection.dart';
import 'package:aistudio_mobile/features/library/models/collection_detail.dart';
import 'package:aistudio_mobile/features/library/models/continue_reading_item.dart';
import 'package:aistudio_mobile/features/library/models/library_statistics.dart';
import 'package:aistudio_mobile/features/library/models/reading_history_item.dart';
import 'package:aistudio_mobile/features/library/models/reading_progress.dart';
import 'package:aistudio_mobile/features/library/models/series_detail.dart';
import 'package:aistudio_mobile/features/library/models/series_summary.dart';
import 'package:aistudio_mobile/features/library/models/tag.dart';
import 'package:aistudio_mobile/features/library/providers/bookmarks_provider.dart';
import 'package:aistudio_mobile/features/library/repositories/library_repository.dart';
import 'package:aistudio_mobile/features/reader/models/adjacent_chapter.dart';
import 'package:aistudio_mobile/features/reader/models/bookmark.dart';
import 'package:aistudio_mobile/shared/providers/repository_providers.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

/// Fake whose [deleteBookmark] can be held pending via a [Completer], so
/// tests can observe the notifier's `actionPending` state mid-flight --
/// mirroring the pattern in updates_provider_test.dart for
/// UpdatesNotifier.deleteTracker.
class _FakeLibraryRepository implements LibraryRepository {
  _FakeLibraryRepository({this.bookmarks = const []});

  List<Bookmark> bookmarks;
  Completer<void>? deleteGate;
  int deleteCallCount = 0;
  bool failDelete = false;

  @override
  Future<Result<List<Bookmark>>> listBookmarks({int limit = 200}) async =>
      Ok(bookmarks.take(limit).toList());

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
    required int seriesId,
    required int chapterId,
    required int page,
    String? note,
  }) =>
      throw UnimplementedError();

  @override
  Future<Result<PagedResult<SeriesSummary>>> listSeries({
    int page = 1,
    int perPage = 20,
    String? sort,
    String? search,
    String? status,
    String? readingStatus,
    int? collectionId,
    int? tagId,
    bool? isFavorite,
    bool? hasChapters,
  }) =>
      throw UnimplementedError();

  @override
  Future<Result<SeriesDetail>> getSeries(int seriesId) => throw UnimplementedError();

  @override
  Future<Result<ChapterDetail>> getChapter(int chapterId) => throw UnimplementedError();

  @override
  Future<Result<List<ContinueReadingItem>>> continueReading({int limit = 20}) =>
      throw UnimplementedError();

  @override
  Future<Result<List<SeriesSummary>>> recentlyAdded({int limit = 20}) =>
      throw UnimplementedError();

  @override
  Future<Result<List<SeriesSummary>>> recentlyUpdated({int limit = 20}) =>
      throw UnimplementedError();

  @override
  Future<Result<List<SeriesSummary>>> recommendations({int limit = 20}) =>
      throw UnimplementedError();

  @override
  Future<Result<List<SeriesSummary>>> search(String query, {int page = 1}) =>
      throw UnimplementedError();

  @override
  Future<Result<ReadingProgress?>> getProgress(int seriesId) => throw UnimplementedError();

  @override
  Future<Result<ReadingProgress>> saveProgress({
    required int seriesId,
    required int chapterId,
    required int lastPage,
  }) =>
      throw UnimplementedError();

  @override
  Future<Result<void>> deleteProgress(int seriesId) => throw UnimplementedError();

  @override
  Future<Result<List<Collection>>> listCollections() => throw UnimplementedError();

  @override
  Future<Result<CollectionDetail>> getCollection(int collectionId) =>
      throw UnimplementedError();

  @override
  Future<Result<Collection>> createCollection({
    required String name,
    String? description,
  }) =>
      throw UnimplementedError();

  @override
  Future<Result<Collection>> updateCollection(
    int collectionId, {
    String? name,
    String? description,
  }) =>
      throw UnimplementedError();

  @override
  Future<Result<void>> deleteCollection(int collectionId) => throw UnimplementedError();

  @override
  Future<Result<void>> addSeriesToCollection(int collectionId, int seriesId) =>
      throw UnimplementedError();

  @override
  Future<Result<void>> removeSeriesFromCollection(int collectionId, int seriesId) =>
      throw UnimplementedError();

  @override
  Future<Result<List<Tag>>> listTags() => throw UnimplementedError();

  @override
  Future<Result<void>> toggleFavorite(int seriesId) => throw UnimplementedError();

  @override
  Future<Result<LibraryStatistics>> statistics() => throw UnimplementedError();

  @override
  Future<Result<List<ReadingHistoryItem>>> readingHistory({int limit = 50}) =>
      throw UnimplementedError();

  @override
  Future<Result<List<ReadingCalendarDay>>> readingCalendar({int days = 30}) =>
      throw UnimplementedError();

  @override
  Future<Result<AdjacentChapter?>> getAdjacentChapter(
    int chapterId, {
    required String direction,
  }) =>
      throw UnimplementedError();
}

Bookmark _bookmark({int id = 1}) => Bookmark(
      id: id,
      seriesId: 10,
      seriesTitle: 'Solo Leveling',
      chapterId: 20,
      chapterTitle: 'Chapter 1',
      page: 3,
      createdAt: DateTime(2026, 1, 1),
    );

void main() {
  group('BookmarksNotifier', () {
    test('lists bookmarks from the repository', () async {
      final repo = _FakeLibraryRepository(bookmarks: [_bookmark(id: 1), _bookmark(id: 2)]);
      final container = ProviderContainer(
        overrides: [libraryRepositoryProvider.overrideWithValue(repo)],
      );
      addTearDown(container.dispose);

      final data = await container.read(bookmarksProvider.future);

      expect(data.bookmarks.length, 2);
      expect(data.actionPending, isFalse);
    });

    test(
        'deleteBookmark sets actionPending immediately, then clears it and '
        'refreshes the list once the delete resolves', () async {
      final repo = _FakeLibraryRepository(bookmarks: [_bookmark(id: 1)])
        ..deleteGate = Completer<void>();
      final container = ProviderContainer(
        overrides: [libraryRepositoryProvider.overrideWithValue(repo)],
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
      final repo = _FakeLibraryRepository(bookmarks: [_bookmark(id: 1)])..failDelete = true;
      final container = ProviderContainer(
        overrides: [libraryRepositoryProvider.overrideWithValue(repo)],
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
