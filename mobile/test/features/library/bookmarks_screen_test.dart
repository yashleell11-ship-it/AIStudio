import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:manhwamaniacs/app/router/routes.dart';
import 'package:manhwamaniacs/core/utils/pagination.dart';
import 'package:manhwamaniacs/core/utils/result.dart';
import 'package:manhwamaniacs/features/library/models/chapter.dart';
import 'package:manhwamaniacs/features/library/models/collection.dart';
import 'package:manhwamaniacs/features/library/models/collection_detail.dart';
import 'package:manhwamaniacs/features/library/models/continue_reading_item.dart';
import 'package:manhwamaniacs/features/library/models/library_statistics.dart';
import 'package:manhwamaniacs/features/library/models/reading_history_item.dart';
import 'package:manhwamaniacs/features/library/models/reading_progress.dart';
import 'package:manhwamaniacs/features/library/models/series_detail.dart';
import 'package:manhwamaniacs/features/library/models/followed_series.dart';
import 'package:manhwamaniacs/features/library/models/tag.dart';
import 'package:manhwamaniacs/features/library/repositories/library_repository.dart';
import 'package:manhwamaniacs/features/library/screens/bookmarks_screen.dart';
import 'package:manhwamaniacs/features/reader/models/adjacent_chapter.dart';
import 'package:manhwamaniacs/features/reader/models/bookmark.dart';
import 'package:manhwamaniacs/shared/providers/repository_providers.dart';

/// Fake used only by the Bookmark Manager screen tests. All other methods
/// throw so a stray call surfaces loudly rather than passing silently with
/// empty data, matching the convention used by the other screen fakes in
/// this repository.
class _FakeLibraryRepository implements LibraryRepository {
  _FakeLibraryRepository({this.bookmarks = const []});

  List<Bookmark> bookmarks;
  int? deletedBookmarkId;
  Completer<void>? deleteGate;

  @override
  Future<Result<List<Bookmark>>> listBookmarks({int limit = 200}) async => Ok(bookmarks);

  @override
  Future<Result<void>> deleteBookmark(int bookmarkId) async {
    deletedBookmarkId = bookmarkId;
    if (deleteGate != null) await deleteGate!.future;
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
  Future<Result<PagedResult<FollowedSeries>>> listSeries({
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
  Future<Result<List<FollowedSeries>>> recentlyAdded({int limit = 20}) =>
      throw UnimplementedError();

  @override
  Future<Result<List<FollowedSeries>>> recentlyUpdated({int limit = 20}) =>
      throw UnimplementedError();

  @override
  Future<Result<List<FollowedSeries>>> recommendations({int limit = 20}) =>
      throw UnimplementedError();

  @override
  Future<Result<List<FollowedSeries>>> search(String query, {int page = 1}) =>
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

Bookmark _bookmark({int id = 1, int page = 3}) => Bookmark(
      id: id,
      seriesId: 10,
      seriesTitle: 'Solo Leveling',
      chapterId: 20,
      chapterTitle: 'Chapter 1',
      page: page,
      note: 'Great scene',
      createdAt: DateTime(2026),
    );

Future<void> _pumpScreen(
  WidgetTester tester, {
  required _FakeLibraryRepository repo,
  void Function(String)? onNavigate,
}) async {
  final router = GoRouter(
    initialLocation: Routes.bookmarks,
    routes: [
      GoRoute(
        path: Routes.bookmarks,
        builder: (_, __) => const BookmarksScreen(),
      ),
      GoRoute(
        path: Routes.reader,
        builder: (_, state) {
          onNavigate?.call(state.uri.toString());
          return const Scaffold(body: Center(child: Text('READER')));
        },
      ),
    ],
  );

  await tester.pumpWidget(
    ProviderScope(
      overrides: [libraryRepositoryProvider.overrideWithValue(repo)],
      child: MaterialApp.router(routerConfig: router),
    ),
  );
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 100));
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('BookmarksScreen', () {
    testWidgets('shows an empty state when there are no bookmarks', (tester) async {
      await _pumpScreen(tester, repo: _FakeLibraryRepository());

      expect(find.text('No bookmarks yet'), findsOneWidget);
    });

    testWidgets('renders bookmark cards with series, chapter, and page', (tester) async {
      await _pumpScreen(
        tester,
        repo: _FakeLibraryRepository(bookmarks: [_bookmark()]),
      );

      expect(find.text('Solo Leveling'), findsOneWidget);
      expect(find.text('Chapter 1'), findsOneWidget);
      expect(find.text('Page 3'), findsOneWidget);
      expect(find.text('Great scene'), findsOneWidget);
    });

    testWidgets('tapping a bookmark navigates to the reader at that page', (tester) async {
      String? navigated;
      await _pumpScreen(
        tester,
        repo: _FakeLibraryRepository(bookmarks: [_bookmark()]),
        onNavigate: (location) => navigated = location,
      );

      await tester.tap(find.text('Solo Leveling'));
      await tester.pumpAndSettle();

      expect(navigated, isNotNull);
      expect(navigated, contains('/library/10/chapters/20/read'));
      expect(navigated, contains('page=3'));
      expect(find.text('READER'), findsOneWidget);
    });

    testWidgets('removing a bookmark calls deleteBookmark and updates the list',
        (tester) async {
      final repo = _FakeLibraryRepository(bookmarks: [_bookmark()]);
      await _pumpScreen(tester, repo: repo);

      expect(find.text('Solo Leveling'), findsOneWidget);

      await tester.tap(find.byIcon(Icons.delete_outline));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      expect(repo.deletedBookmarkId, 1);
      expect(find.text('No bookmarks yet'), findsOneWidget);
    });

    testWidgets('disables the delete button while a removal is pending', (tester) async {
      final repo = _FakeLibraryRepository(bookmarks: [_bookmark()])
        ..deleteGate = Completer<void>();
      await _pumpScreen(tester, repo: repo);

      await tester.tap(find.byIcon(Icons.delete_outline));
      await tester.pump();

      final button = tester.widget<IconButton>(
        find.ancestor(
          of: find.byIcon(Icons.delete_outline),
          matching: find.byType(IconButton),
        ),
      );
      expect(button.onPressed, isNull);

      repo.deleteGate!.complete();
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      expect(find.text('No bookmarks yet'), findsOneWidget);
    });
  });
}