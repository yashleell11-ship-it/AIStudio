import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/core/utils/result.dart';
import 'package:manhwamaniacs/features/downloads/providers/downloads_scope.dart';
import 'package:manhwamaniacs/features/reader/models/bookmark.dart';
import 'package:manhwamaniacs/features/reader/models/chapter_manifest.dart';
import 'package:manhwamaniacs/features/reader/models/chapter_manifest_window.dart';
import 'package:manhwamaniacs/features/reader/models/reader_feed.dart';
import 'package:manhwamaniacs/features/reader/models/reading_progress.dart';
import 'package:manhwamaniacs/features/reader/providers/reader_chapter_provider.dart';
import 'package:manhwamaniacs/features/reader/providers/series_reading_order_provider.dart';
import 'package:manhwamaniacs/features/reader/repositories/reader_repository.dart';
import 'package:manhwamaniacs/features/reader/screens/reader_screen.dart';
import 'package:manhwamaniacs/features/reader/widgets/reader_content.dart';
import 'package:manhwamaniacs/shared/providers/core_providers.dart';
import 'package:manhwamaniacs/shared/providers/repository_providers.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../support/test_overrides.dart';

/// The owner, twice over two releases: "while reading the mmanhwa in alll
/// together after 2-3 chapter it sends me back to 2-3 back i have to get back
/// to position again and again".
///
/// The reconciliation inside [ReaderContent] was fixed and proved. What was
/// left is one rung up: [ReaderScreen] rebuilt its whole feed controller
/// whenever `resolvedReaderChapterProvider` re-emitted, because it compared
/// the incoming chapter by REFERENCE — and that provider builds a fresh
/// [ReaderChapter] on every run, so the guard was false however identical the
/// value. A rebuilt controller starts at `ReaderFeed.single(anchor)`: the
/// window collapses onto the chapter the ROUTE opened at, which after reading
/// forward two or three chapters is a jump two or three chapters back, and it
/// recurs on every re-emission.
///
/// So these tests do not assert about a guard. They read forward until the
/// Read-all window genuinely holds several chapters, make the provider
/// re-emit an EQUIVALENT chapter, and assert the reader did not move.

const _sourceId = 'asurascans';
const _seriesKey = 'solo-leveling';
const _anchorKey = 'ch-1';
const _chapterCount = 6;
const _pagesPerChapter = 8;

ChapterManifestKey _keyFor(String chapterKey) =>
    (sourceId: _sourceId, seriesKey: _seriesKey, chapterKey: chapterKey);

List<String> get _order => [for (var n = 1; n <= _chapterCount; n++) 'ch-$n'];

/// A manifest built fresh on every call — exactly like the real repository,
/// and the whole reason reference equality was never going to hold.
ChapterManifest _manifestFor(String chapterKey, {required String pagePrefix}) {
  final index = _order.indexOf(chapterKey);
  return ChapterManifest(
    sourceId: _sourceId,
    seriesKey: _seriesKey,
    chapterKey: chapterKey,
    chapterNumber: (index + 1).toDouble(),
    pageCount: _pagesPerChapter,
    prev: index > 0 ? _order[index - 1] : null,
    next: index < _order.length - 1 ? _order[index + 1] : null,
    pages: [
      for (var n = 1; n <= _pagesPerChapter; n++)
        ManifestPage(number: n, url: '$pagePrefix/$chapterKey/$n'),
    ],
  );
}

class _FakeReaderRepository implements ReaderRepository {
  /// Where this source says its pages live. Mutable so a test can make the
  /// SAME chapter resolve to different bytes — a chapter that finished
  /// downloading mid-read is exactly that.
  String pagePrefix = '/sources/$_sourceId';

  @override
  Future<Result<ChapterManifest>> manifest({
    required String sourceId,
    required String seriesKey,
    required String chapterKey,
  }) async =>
      Ok(_manifestFor(chapterKey, pagePrefix: pagePrefix));

  @override
  Future<Result<ReadingProgress>> saveProgress(ProgressPush push) async => Ok(
        ReadingProgress(
          id: 1,
          sourceId: push.sourceId,
          seriesKey: push.seriesKey,
          chapterKey: push.chapterKey,
          chapterNumber: push.chapterNumber,
          lastPage: push.lastPage,
          pageCount: push.pageCount,
          scrollOffsetPx: push.scrollOffsetPx,
          isCompleted: push.isCompleted,
          timeSpentSeconds: push.timeSpentSeconds,
        ),
      );

  @override
  Future<Result<({int saved, int advanced})>> saveProgressBatch(
    List<ProgressPush> pushes,
  ) async =>
      Ok((saved: pushes.length, advanced: 0));

  @override
  Future<Result<List<ReadingProgress>>> seriesProgress({
    required String sourceId,
    required String seriesKey,
  }) async =>
      const Ok([]);

  @override
  Future<Result<BookmarkSyncResult>> syncBookmarks(List<BookmarkOp> ops) async =>
      Ok(
        BookmarkSyncResult(
          received: ops.length,
          created: ops.length,
          updated: 0,
          tombstoned: 0,
          rejected: 0,
          serverIds: {for (final op in ops) op.bookmark.clientId: 1},
        ),
      );

  @override
  Future<Result<List<Bookmark>>> listBookmarks({
    String? sourceId,
    String? seriesKey,
    DateTime? since,
    bool includeDeleted = false,
    int? limit,
  }) async =>
      const Ok([]);

  @override
  Future<Result<void>> deleteBookmark(int bookmarkId) async => const Ok(null);

  @override
  Future<Result<ChapterManifestWindow>> manifestWindow({
    required String sourceId,
    required String seriesKey,
    required List<String> chapterKeys,
  }) =>
      throw UnimplementedError();
}

/// The reader's own scroll view — the one whose offset "sends me back" is
/// measured in.
ScrollController _listController(WidgetTester tester) =>
    tester.widget<ListView>(find.byType(ListView)).controller!;

ReaderFeed _feed(WidgetTester tester) =>
    tester.widget<ReaderContent>(find.byType(ReaderContent)).feed;

List<String> _feedChapterIds(WidgetTester tester) =>
    [for (final chapter in _feed(tester).chapters) chapter.id];

/// Pumps without settling: the reader keeps a controls-hiding timer and a
/// progress debounce alive, so `pumpAndSettle` would never return.
Future<void> _tick(WidgetTester tester, [int frames = 8]) async {
  for (var i = 0; i < frames; i++) {
    await tester.pump(const Duration(milliseconds: 50));
  }
}

/// Read forward the way the owner does — to the end of what is loaded, over
/// and over — until the window holds [chapters] of them.
Future<void> _readForwardUntilFeedHolds(
  WidgetTester tester,
  int chapters,
) async {
  for (var attempt = 0; attempt < 12; attempt++) {
    if (_feed(tester).chapters.length >= chapters) return;
    final controller = _listController(tester);
    controller.jumpTo(controller.position.maxScrollExtent);
    await _tick(tester);
  }
  fail(
    'the feed never grew to $chapters chapters — it holds '
    '${_feedChapterIds(tester)}',
  );
}

/// Keep reading forward until the window has slid far enough that the chapter
/// the ROUTE opened at has been released — the state the report describes,
/// where a collapse back to the anchor is a jump right out of the run.
Future<void> _readPastTheAnchor(WidgetTester tester) async {
  for (var attempt = 0; attempt < 12; attempt++) {
    if (!_feed(tester).contains(_anchorKey)) return;
    final controller = _listController(tester);
    controller.jumpTo(controller.position.maxScrollExtent);
    await _tick(tester);
  }
  fail('the window never slid past $_anchorKey');
}

typedef _Harness = ({ProviderContainer container, _FakeReaderRepository repo});

Future<_Harness> _openReadAll(WidgetTester tester) async {
  SharedPreferences.setMockInitialValues(testPrefsDefaults());
  final prefs = await SharedPreferences.getInstance();
  final repo = _FakeReaderRepository();

  await tester.binding.setSurfaceSize(const Size(430, 932));
  addTearDown(() => tester.binding.setSurfaceSize(null));

  await tester.pumpWidget(
    ProviderScope(
      overrides: [
        sharedPrefsProvider.overrideWithValue(prefs),
        apiBaseUrlOverride('http://example.test'),
        readerRepositoryProvider.overrideWithValue(repo),
        // No `(user, profile)` scope in this test, so no on-device store —
        // stated rather than left to the auth default, since the resolved
        // provider watches it and a store appearing mid-test would be a
        // re-emission the test did not ask for.
        downloadsStoreProvider.overrideWithValue(null),
        // Read-all's chapter order. The real one comes from series detail;
        // what matters here is only that the feed knows where it is going.
        seriesReadingOrderProvider((sourceId: _sourceId, seriesId: _seriesKey))
            .overrideWith((ref) async => _order),
      ],
      child: const MaterialApp(
        home: ReaderScreen(
          sourceId: _sourceId,
          seriesKey: _seriesKey,
          chapterKey: _anchorKey,
          readAll: true,
        ),
      ),
    ),
  );
  await _tick(tester);

  expect(
    find.byType(ReaderContent),
    findsOneWidget,
    reason: 'the reader should have painted before the test drives it',
  );
  return (
    container: ProviderScope.containerOf(
      tester.element(find.byType(ReaderScreen)),
    ),
    repo: repo,
  );
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('a Read-all window survives the anchor re-resolving', () {
    testWidgets('an equivalent re-emission moves nothing', (tester) async {
      final harness = await _openReadAll(tester);
      await _readForwardUntilFeedHolds(tester, 2);

      final chaptersBefore = _feedChapterIds(tester);
      final offsetBefore = _listController(tester).offset;
      expect(
        chaptersBefore.length,
        greaterThan(1),
        reason: 'the window has to hold a run for there to be one to lose',
      );

      // The re-emission itself. The fake repository builds a fresh manifest
      // every call, so what comes back is a NEW ReaderChapter carrying the
      // exact same chapter — which is the whole shape of the bug.
      harness.container.invalidate(
        resolvedReaderChapterProvider(_keyFor(_anchorKey)),
      );
      await _tick(tester);

      expect(
        _feedChapterIds(tester),
        chaptersBefore,
        reason: 'nothing about the chapter changed, so nothing should have '
            'been thrown away',
      );
      expect(
        _listController(tester).offset,
        offsetBefore,
        reason: 'the reader was not reading the provider, they were reading '
            'the page they were on',
      );
    });

    testWidgets(
        'a re-emission of a chapter the window has slid past is ignored',
        (tester) async {
      final harness = await _openReadAll(tester);
      await _readPastTheAnchor(tester);

      final chaptersBefore = _feedChapterIds(tester);
      final offsetBefore = _listController(tester).offset;
      expect(
        chaptersBefore,
        isNot(contains(_anchorKey)),
        reason: 'this is the case the report describes — reading has moved on '
            'from the chapter the route opened at',
      );

      harness.container.invalidate(
        resolvedReaderChapterProvider(_keyFor(_anchorKey)),
      );
      await _tick(tester);

      // The old guard rebuilt the controller here, and a rebuilt controller
      // starts at ReaderFeed.single(anchor) — so the reader landed back at
      // ch-1 with the rest of the run gone. That is "it sends me back 2-3".
      expect(
        _feedChapterIds(tester),
        chaptersBefore,
        reason: 'a chapter no longer on screen has no business rebuilding the '
            'feed around itself',
      );
      expect(_listController(tester).offset, offsetBefore);
    });

    testWidgets('a genuinely different chapter still reaches the feed',
        (tester) async {
      final harness = await _openReadAll(tester);
      await _readForwardUntilFeedHolds(tester, 2);

      final chaptersBefore = _feedChapterIds(tester);
      expect(chaptersBefore, contains(_anchorKey));

      // Same chapter key, genuinely different pages — the shape of a chapter
      // whose bytes moved under it mid-read. The window is kept, but the new
      // pages still have to land in it: a guard that ignored this would trade
      // one bug for a staler one.
      harness.repo.pagePrefix = '/elsewhere';
      harness.container
        ..invalidate(chapterManifestProvider(_keyFor(_anchorKey)))
        ..invalidate(resolvedReaderChapterProvider(_keyFor(_anchorKey)));
      await _tick(tester);

      expect(
        _feedChapterIds(tester),
        chaptersBefore,
        reason: 'a changed chapter is folded in, not started over from',
      );
      final anchor = _feed(tester)
          .chapters
          .firstWhere((chapter) => chapter.id == _anchorKey);
      expect(
        anchor.pages.first.imageUrl,
        contains('/elsewhere/'),
        reason: 'the re-resolved pages are the ones that should be rendering',
      );
    });
  });
}
