import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/core/utils/pagination.dart';
import 'package:manhwamaniacs/core/utils/result.dart';
import 'package:manhwamaniacs/features/downloads/models/chapter_identity.dart';
import 'package:manhwamaniacs/features/downloads/models/chapter_selection.dart';
import 'package:manhwamaniacs/features/downloads/models/saved_chapter.dart';
import 'package:manhwamaniacs/features/downloads/providers/downloads_scope.dart';
import 'package:manhwamaniacs/features/downloads/queue/download_queue_controller.dart';
import 'package:manhwamaniacs/features/reader/models/reader_chapter.dart';
import 'package:manhwamaniacs/features/sources/models/source.dart';
import 'package:manhwamaniacs/features/sources/models/source_pin.dart';
import 'package:manhwamaniacs/features/sources/models/source_search_group.dart';
import 'package:manhwamaniacs/features/sources/models/source_series.dart';
import 'package:manhwamaniacs/features/sources/repositories/sources_repository.dart';
import 'package:manhwamaniacs/features/sources/screens/source_series_detail_screen.dart';
import 'package:manhwamaniacs/shared/providers/core_providers.dart';
import 'package:manhwamaniacs/shared/providers/repository_providers.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../support/downloads_test_support.dart';
import '../../support/test_overrides.dart';

/// Bulk chapter download (spec R4): "get multi download back so i can download
/// 10 chapters in 1 go".
///
/// The load-bearing assertion is not that ten rows get ticked — it is that the
/// ten arrive at [DownloadQueueController.enqueueChapters], the same door the
/// single-chapter button and "Download Series" use. Bulk must not have a fast
/// path around the storage cap, the free-space floor, pause/resume or per-item
/// retry, and a recording queue is how that is checked without re-testing the
/// engine those guards live in.
class _RecordingQueue extends DownloadQueueController {
  final List<List<ChapterQueueRequest>> batches = [];
  final List<ChapterIdentity> singles = [];

  @override
  Future<void> enqueueChapters(Iterable<ChapterQueueRequest> chapters) async {
    batches.add(chapters.toList());
  }

  @override
  Future<void> enqueueChapter({
    required ChapterIdentity id,
    double? chapterNumber,
    String? title,
    String? seriesTitle,
    DownloadKind kind = DownloadKind.manga,
  }) async {
    singles.add(id);
  }
}

class _FakeSourcesRepository implements SourcesRepository {
  _FakeSourcesRepository(this.chapters);

  final List<SourceChapterSummary> chapters;

  @override
  Future<Result<SourceSeriesSummary>> getSeries(String s, String i) async =>
      const Ok(
        SourceSeriesSummary(
          id: 'manga-1',
          sourceId: 'mangadex',
          title: 'Solo Leveling',
          chapterCount: 30,
          genres: [],
          coverUrl: '',
        ),
      );

  @override
  Future<Result<List<SourceChapterSummary>>> getChapters(String s, String i) async =>
      Ok(chapters);

  @override
  Future<Result<List<SourceSummary>>> listSources() => throw UnimplementedError();

  @override
  Future<Result<GroupedSearchResult>> searchGrouped(
    String query, {
    int page = 1,
    int perPage = 40,
  }) =>
      throw UnimplementedError();

  @override
  Future<Result<List<SourcePin>>> listPins() => throw UnimplementedError();

  @override
  Future<Result<List<SourcePin>>> replacePins(List<String> sourceIds) =>
      throw UnimplementedError();

  @override
  Future<Result<List<SourceBrowseMode>>> listBrowseModes(String sourceId) =>
      throw UnimplementedError();

  @override
  Future<Result<PagedResult<SourceSeriesSummary>>> listSeries(
    String sourceId, {
    int page = 1,
    String? query,
    String? sort,
  }) =>
      throw UnimplementedError();

  @override
  Future<Result<ReaderChapter>> getReaderChapter(String s, String i, String c) =>
      throw UnimplementedError();
}

List<SourceChapterSummary> _chapters(int count) => [
      for (var i = 1; i <= count; i++)
        SourceChapterSummary(
          id: 'ch-$i',
          sourceId: 'mangadex',
          seriesId: 'manga-1',
          title: 'Chapter $i',
          number: i.toDouble(),
          pageCount: 10,
        ),
    ];

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  initSqfliteFfiForTests();

  late TestDownloadsHarness harness;

  setUp(() async {
    harness = await TestDownloadsHarness.create();
  });

  tearDown(() async {
    await harness.dispose();
  });

  Future<_RecordingQueue> pumpSeriesPage(
    WidgetTester tester, {
    int chapterCount = 30,
  }) async {
    SharedPreferences.setMockInitialValues({});
    final prefs = await SharedPreferences.getInstance();
    final queue = _RecordingQueue();

    final container = ProviderContainer(
      overrides: [
        sharedPrefsProvider.overrideWithValue(prefs),
        apiBaseUrlOverride('http://example.test'),
        sourcesRepositoryProvider
            .overrideWithValue(_FakeSourcesRepository(_chapters(chapterCount))),
        // A real (empty) store plus a resolvable scope: the download
        // affordances only exist when there is somewhere to download into.
        activeDownloadsScopeIdProvider.overrideWithValue('u1p1'),
        downloadsStoreProvider.overrideWithValue(harness.storeFor('u1p1')),
        downloadQueueControllerProvider.overrideWith(() => queue),
      ],
    );
    addTearDown(container.dispose);

    await tester.binding.setSurfaceSize(const Size(430, 1800));
    addTearDown(() => tester.binding.setSurfaceSize(null));

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(
          home: SourceSeriesDetailScreen(
            sourceId: 'mangadex',
            seriesId: 'manga-1',
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    return queue;
  }

  testWidgets('the chapter list is not selectable until asked', (tester) async {
    await pumpSeriesPage(tester);

    expect(find.byKey(const Key('select-chapters')), findsOneWidget);
    // No checkbox anywhere: an untouched chapter list looks exactly as it did.
    expect(find.byType(Checkbox), findsNothing);
    expect(find.byKey(const Key('download-selected')), findsNothing);
  });

  testWidgets('Select reveals the checkboxes and the range helpers',
      (tester) async {
    await pumpSeriesPage(tester);

    await tester.tap(find.byKey(const Key('select-chapters')));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('select-next-10')), findsOneWidget);
    expect(find.byKey(const Key('select-all-unread')), findsOneWidget);
    expect(find.byKey(const Key('select-all-chapters')), findsOneWidget);
    expect(find.byType(Checkbox), findsWidgets);
  });

  testWidgets(
      '"Next 10" then Download queues exactly ten chapters, in reading order, '
      'through the ordinary queue', (tester) async {
    final queue = await pumpSeriesPage(tester);

    await tester.tap(find.byKey(const Key('select-chapters')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('select-next-10')));
    await tester.pumpAndSettle();

    expect(
      find.text('Download $kQuickRangeChapterCount chapters'),
      findsOneWidget,
      reason: 'the button must say how many it is about to queue',
    );

    await tester.tap(find.byKey(const Key('download-selected')));
    await tester.pumpAndSettle();

    expect(queue.batches, hasLength(1));
    final batch = queue.batches.single;
    expect(batch, hasLength(10));
    // Oldest first, regardless of the list's Newest-first display sort — the
    // queue reads chapter 1 before chapter 10.
    expect(batch.first.id.chapterKey, 'ch-1');
    expect(batch.last.id.chapterKey, 'ch-10');
    expect(batch.first.chapterNumber, 1);
    expect(batch.first.seriesTitle, 'Solo Leveling');
    // Not one call per chapter: ten separate enqueues would cost the
    // store-backed lists ten refreshes.
    expect(queue.singles, isEmpty);
  });

  testWidgets('selection is left behind once the batch is queued',
      (tester) async {
    await pumpSeriesPage(tester);

    await tester.tap(find.byKey(const Key('select-chapters')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('select-next-10')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('download-selected')));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('select-chapters')), findsOneWidget);
    expect(find.byType(Checkbox), findsNothing);
  });

  testWidgets('tapping a row while selecting ticks it instead of opening it',
      (tester) async {
    final queue = await pumpSeriesPage(tester, chapterCount: 3);

    await tester.tap(find.byKey(const Key('select-chapters')));
    await tester.pumpAndSettle();

    // The row itself, not its checkbox: a tap anywhere on a chapter must
    // tick it while selecting, or the checkbox is the only target and the
    // mode is worse to use than the thing it replaced.
    await tester.tap(find.text('Chapter 2'));
    await tester.pumpAndSettle();
    expect(find.text('Download 1 chapter'), findsOneWidget);

    // And the checkbox does the same thing.
    await tester.tap(find.byKey(const Key('select-ch-3')));
    await tester.pumpAndSettle();
    expect(find.text('Download 2 chapters'), findsOneWidget);

    await tester.tap(find.byKey(const Key('download-selected')));
    await tester.pumpAndSettle();

    expect(
      [for (final r in queue.batches.single) r.id.chapterKey],
      ['ch-2', 'ch-3'],
    );
  });

  testWidgets('Cancel leaves the mode without queueing anything',
      (tester) async {
    final queue = await pumpSeriesPage(tester, chapterCount: 3);

    await tester.tap(find.byKey(const Key('select-chapters')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('select-all-chapters')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('cancel-selection')));
    await tester.pumpAndSettle();

    expect(queue.batches, isEmpty);
    expect(find.byType(Checkbox), findsNothing);
  });
}
