import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
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
import 'package:manhwamaniacs/features/library/models/series_summary.dart';
import 'package:manhwamaniacs/features/library/models/tag.dart';
import 'package:manhwamaniacs/features/library/providers/series_detail_provider.dart';
import 'package:manhwamaniacs/features/library/repositories/library_repository.dart';
import 'package:manhwamaniacs/features/library/screens/series_detail_screen.dart';
import 'package:manhwamaniacs/features/reader/models/adjacent_chapter.dart';
import 'package:manhwamaniacs/features/reader/models/bookmark.dart';
import 'package:manhwamaniacs/features/updates/models/series_tracker.dart';
import 'package:manhwamaniacs/features/updates/models/update_notification.dart';
import 'package:manhwamaniacs/features/updates/repositories/updates_repository.dart';
import 'package:manhwamaniacs/shared/providers/core_providers.dart';
import 'package:manhwamaniacs/shared/providers/repository_providers.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../../support/test_overrides.dart';

class _FakeSeriesDetailRepository implements LibraryRepository {
  _FakeSeriesDetailRepository(this.detail);

  final SeriesDetail detail;

  @override
  Future<Result<SeriesDetail>> getSeries(int seriesId) async => Ok(detail);

  @override
  Future<Result<void>> toggleFavorite(int seriesId) async => const Ok(null);

  @override
  Future<Result<void>> deleteProgress(int seriesId) => throw UnimplementedError();

  @override
  Future<Result<ChapterDetail>> getChapter(int chapterId) => throw UnimplementedError();

  @override
  Future<Result<ReadingProgress?>> getProgress(int seriesId) => throw UnimplementedError();

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
  Future<Result<ReadingProgress>> saveProgress({
    required int seriesId,
    required int chapterId,
    required int lastPage,
  }) =>
      throw UnimplementedError();

  @override
  Future<Result<List<SeriesSummary>>> search(String query, {int page = 1}) =>
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
  Future<Result<LibraryStatistics>> statistics() => throw UnimplementedError();

  @override
  Future<Result<List<ReadingHistoryItem>>> readingHistory({int limit = 50}) =>
      throw UnimplementedError();

  @override
  Future<Result<List<ReadingCalendarDay>>> readingCalendar({int days = 30}) =>
      throw UnimplementedError();

  @override
  Future<Result<Bookmark>> addBookmark({
    required int seriesId,
    required int chapterId,
    required int page,
    String? note,
  }) =>
      throw UnimplementedError();

  @override
  Future<Result<List<Bookmark>>> listBookmarks({int limit = 200}) async => const Ok([]);

  @override
  Future<Result<void>> deleteBookmark(int bookmarkId) async => const Ok(null);

  @override
  Future<Result<AdjacentChapter?>> getAdjacentChapter(
    int chapterId, {
    required String direction,
  }) =>
      throw UnimplementedError();
}

/// Fake updates repository backing the Follow control. Records which tracker
/// endpoint was hit so the tests can tell Follow (POST /updates/trackers/follow)
/// from Unfollow (DELETE /updates/trackers/{id}) apart, and echoes new follows
/// back through [listTrackers] the way the server would.
class _FakeUpdatesRepository implements UpdatesRepository {
  _FakeUpdatesRepository({this.trackers = const []});

  List<SeriesTracker> trackers;
  String? followedSource;
  String? followedSeriesId;
  String? followedTitle;
  int? deletedTrackerId;

  /// When set, [listTrackers] awaits this, so a test can hold the trackers
  /// cache in flight and assert what the button renders from the payload alone.
  Completer<void>? listTrackersGate;

  @override
  Future<Result<void>> followSeries({
    required String source,
    required String seriesId,
    required String seriesTitle,
  }) async {
    followedSource = source;
    followedSeriesId = seriesId;
    followedTitle = seriesTitle;
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
    deletedTrackerId = trackerId;
    trackers = trackers.where((t) => t.id != trackerId).toList();
    return const Ok(null);
  }

  @override
  Future<Result<List<SeriesTracker>>> listTrackers() async {
    if (listTrackersGate != null) await listTrackersGate!.future;
    return Ok(trackers);
  }

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

  @override
  Future<Result<void>> updateTracker(int trackerId, {bool? autoDownload}) =>
      throw UnimplementedError();
}

SeriesDetail _sampleSeriesDetail({
  String? sourceId,
  String? sourceSeriesId,
  bool isFollowed = false,
  int? followTrackerId,
}) {
  return SeriesDetail(
    sourceId: sourceId,
    sourceSeriesId: sourceSeriesId,
    isFollowed: isFollowed,
    followTrackerId: followTrackerId,
    id: 1,
    libraryId: 1,
    title: 'Solo Leveling',
    sortTitle: 'solo leveling',
    originalTitle: 'Na Honjaman Level Up',
    author: 'Chugong',
    artist: 'Dubu',
    description: 'The weakest hunter becomes the strongest.',
    status: 'completed',
    contentRating: 'teen',
    language: 'ko',
    year: 2018,
    folderPath: '/library/solo-leveling',
    isFavorite: true,
    readingStatus: 'reading',
    chapterCount: 2,
    readChapters: 1,
    pageCount: 40,
    totalChapters: 2,
    totalPages: 40,
    firstChapterId: 101,
    createdAt: DateTime(2024),
    updatedAt: DateTime(2024, 6),
    readingProgress: ReadingProgress(
      seriesId: 1,
      chapterId: 101,
      lastPage: 5,
      progressPct: 50,
      lastReadAt: DateTime(2024, 6),
    ),
    chapters: const [
      ChapterSummary(
        id: 101,
        seriesId: 1,
        title: 'Chapter 1',
        number: 1,
        pageCount: 20,
      ),
      ChapterSummary(
        id: 102,
        seriesId: 1,
        title: 'Chapter 2',
        number: 2,
        pageCount: 20,
      ),
    ],
    tags: const [],
    collections: const [CollectionRef(id: 1, name: 'Favorites')],
  );
}

Future<Widget> _buildSeriesDetailApp(
  SeriesDetail detail, {
  _FakeUpdatesRepository? updatesRepo,
}) async {
  SharedPreferences.setMockInitialValues({});
  final prefs = await SharedPreferences.getInstance();

  return ProviderScope(
    overrides: [
      apiBaseUrlOverride('http://127.0.0.1:8000'),
      sharedPrefsProvider.overrideWithValue(prefs),
      libraryRepositoryProvider.overrideWithValue(
        _FakeSeriesDetailRepository(detail),
      ),
      updatesRepositoryProvider.overrideWithValue(
        updatesRepo ?? _FakeUpdatesRepository(),
      ),
      seriesDetailProvider(1).overrideWith((ref) async => detail),
    ],
    child: const MaterialApp(
      home: SeriesDetailScreen(seriesId: 1),
    ),
  );
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('SeriesDetailScreen', () {
    testWidgets('renders series metadata and chapters', (tester) async {
      tester.view.physicalSize = const Size(1080, 2400);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);

      await tester.pumpWidget(await _buildSeriesDetailApp(_sampleSeriesDetail()));
      await tester.pumpAndSettle();

      expect(find.text('Solo Leveling'), findsWidgets);
      expect(find.text('by Chugong'), findsOneWidget);
      expect(find.text('Chapter 1'), findsOneWidget);
      expect(find.text('Reading'), findsOneWidget);
      expect(find.textContaining('Favorites'), findsOneWidget);
    });
  });

  group('SeriesDetailScreen Follow control', () {
    /// Widens the surface so the whole detail column lays out; the Follow
    /// control sits below the read CTA and would otherwise be off-screen.
    void useTallSurface(WidgetTester tester) {
      tester.view.physicalSize = const Size(1080, 2400);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);
    }

    testWidgets('is absent for a series with no source link', (tester) async {
      useTallSurface(tester);
      final fakeUpdates = _FakeUpdatesRepository();

      // A hand-imported CBZ folder: source_id/source_series_id are null, so
      // there is nothing to track and no control should be offered at all --
      // not even a disabled one.
      await tester.pumpWidget(
        await _buildSeriesDetailApp(
          _sampleSeriesDetail(),
          updatesRepo: fakeUpdates,
        ),
      );
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('follow-toggle')), findsNothing);
      expect(find.text('Follow'), findsNothing);
      expect(find.text('Unfollow'), findsNothing);
    });

    testWidgets('shows Follow for an unfollowed source-linked series and '
        'following flips it to Unfollow', (tester) async {
      useTallSurface(tester);
      final fakeUpdates = _FakeUpdatesRepository();

      await tester.pumpWidget(
        await _buildSeriesDetailApp(
          _sampleSeriesDetail(
            sourceId: 'mangadex',
            sourceSeriesId: 'manga-1',
          ),
          updatesRepo: fakeUpdates,
        ),
      );
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('follow-toggle')), findsOneWidget);
      expect(find.text('Follow'), findsOneWidget);

      await tester.ensureVisible(find.text('Follow'));
      await tester.tap(find.text('Follow'));
      await tester.pumpAndSettle();

      // The tracker API renames the pair: source_id -> source,
      // source_series_id -> series_id.
      expect(fakeUpdates.followedSource, 'mangadex');
      expect(fakeUpdates.followedSeriesId, 'manga-1');
      expect(fakeUpdates.followedTitle, 'Solo Leveling');
      expect(find.text('Unfollow'), findsOneWidget);
      expect(find.text('Follow'), findsNothing);
    });

    testWidgets('reflects the already-followed state from the payload before '
        'the trackers list loads', (tester) async {
      useTallSurface(tester);
      final fakeUpdates = _FakeUpdatesRepository(
        trackers: [
          const SeriesTracker(
            id: 42,
            source: 'mangadex',
            seriesId: 'manga-1',
            seriesTitle: 'Solo Leveling',
            trackKind: TrackKind.followed,
            enabled: true,
            notify: true,
            autoDownload: false,
            knownChapterCount: 0,
          ),
        ],
      )..listTrackersGate = Completer<void>();

      await tester.pumpWidget(
        await _buildSeriesDetailApp(
          _sampleSeriesDetail(
            sourceId: 'mangadex',
            sourceSeriesId: 'manga-1',
            isFollowed: true,
            followTrackerId: 42,
          ),
          updatesRepo: fakeUpdates,
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      // The trackers request is still gated, so this label can only have come
      // from the detail payload -- the point of shipping is_followed on it.
      expect(find.text('Unfollow'), findsOneWidget);
      expect(find.text('Follow'), findsNothing);

      // ...but the control stays disabled until the cache lands, so a tap can
      // never act on a tracker id the payload named and the server has since
      // dropped.
      final button = tester.widget<FilledButton>(
        find.ancestor(
          of: find.text('Unfollow'),
          matching: find.byType(FilledButton),
        ),
      );
      expect(button.onPressed, isNull);

      fakeUpdates.listTrackersGate!.complete();
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      expect(find.text('Unfollow'), findsOneWidget);
    });

    testWidgets('unfollowing deletes the tracker the payload named',
        (tester) async {
      useTallSurface(tester);
      final fakeUpdates = _FakeUpdatesRepository(
        trackers: [
          const SeriesTracker(
            id: 42,
            source: 'mangadex',
            seriesId: 'manga-1',
            seriesTitle: 'Solo Leveling',
            trackKind: TrackKind.followed,
            enabled: true,
            notify: true,
            autoDownload: false,
            knownChapterCount: 0,
          ),
        ],
      );

      await tester.pumpWidget(
        await _buildSeriesDetailApp(
          _sampleSeriesDetail(
            sourceId: 'mangadex',
            sourceSeriesId: 'manga-1',
            isFollowed: true,
            followTrackerId: 42,
          ),
          updatesRepo: fakeUpdates,
        ),
      );
      await tester.pumpAndSettle();

      await tester.ensureVisible(find.text('Unfollow'));
      await tester.tap(find.text('Unfollow'));
      await tester.pumpAndSettle();

      expect(fakeUpdates.deletedTrackerId, 42);
      expect(find.text('Follow'), findsOneWidget);
      expect(find.text('Unfollow'), findsNothing);
    });

    testWidgets('a downloaded-only tracker does not count as followed',
        (tester) async {
      useTallSurface(tester);
      // Every downloaded series gets a `downloaded` tracker; if the button
      // treated those as follows, every downloaded series would render as
      // already-followed and could never be followed for real.
      final fakeUpdates = _FakeUpdatesRepository(
        trackers: [
          const SeriesTracker(
            id: 7,
            source: 'mangadex',
            seriesId: 'manga-1',
            seriesTitle: 'Solo Leveling',
            trackKind: TrackKind.downloaded,
            enabled: true,
            notify: false,
            autoDownload: false,
            knownChapterCount: 0,
          ),
        ],
      );

      await tester.pumpWidget(
        await _buildSeriesDetailApp(
          _sampleSeriesDetail(
            sourceId: 'mangadex',
            sourceSeriesId: 'manga-1',
          ),
          updatesRepo: fakeUpdates,
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Follow'), findsOneWidget);
      expect(find.text('Unfollow'), findsNothing);
    });
  });
}