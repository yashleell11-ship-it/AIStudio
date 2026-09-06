import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/features/downloads/providers/downloads_scope.dart';
import 'package:manhwamaniacs/features/reader/models/reader_chapter.dart';
import 'package:manhwamaniacs/features/reader/models/reader_feed.dart';
import 'package:manhwamaniacs/features/reader/models/reader_page.dart';
import 'package:manhwamaniacs/features/reader/providers/series_reading_order_provider.dart';
import 'package:manhwamaniacs/features/reader/utils/reader_feed_controller.dart';
import 'package:manhwamaniacs/features/reader/widgets/reader_content.dart';
import 'package:manhwamaniacs/features/sources/providers/source_reader_provider.dart';
import 'package:manhwamaniacs/features/sources/screens/source_reader_screen.dart';
import 'package:manhwamaniacs/shared/providers/core_providers.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../support/test_overrides.dart';

/// Watched by the payload override so a test can make the chapter provider
/// RELOAD — a dependency change, not an invalidate — on demand. In the app
/// that dependency is the repository behind the payload, which follows the
/// API base URL.
final _payloadDependencyBump = StateProvider<int>((_) => 0);

/// The owner, a third time: "there are still error with the scroll its
/// improved but yea it still sends back".
///
/// The library reader was fixed and proved (reader_feed_reemission_test).
/// The SOURCE reader — the one every "Read all" tapped from a browsed series
/// opens — had the same bug by a different route: it decided on every build
/// whether to keep its feed by asking whether the window still held the
/// chapter the ROUTE opened at. A Read-all window slides forward by dropping
/// its oldest chapter, so exactly three chapters in that answer becomes "no",
/// and the very next build — the one the slide itself schedules — threw the
/// window away and started over from the entry chapter. That is "after 2-3
/// chapters it sends me back 2-3 back", and it recurs every three chapters.
///
/// So these tests read forward through a browsed series until the window has
/// slid past the entry chapter, and assert the reader stays there.

const _sourceId = 'asurascans';
const _seriesId = 'solo-leveling';
const _anchorId = 'ch-1';
const _chapterCount = 6;
const _pagesPerChapter = 8;

SourceReaderChapterKey _keyFor(String chapterId) =>
    (sourceId: _sourceId, seriesId: _seriesId, chapterId: chapterId);

List<String> get _order => [for (var n = 1; n <= _chapterCount; n++) 'ch-$n'];

/// Built fresh on every call, like the real repository: a re-resolution is
/// always a NEW object carrying the same chapter.
ReaderChapter _chapterFor(String chapterId, {String pagePrefix = '/pages'}) {
  final index = _order.indexOf(chapterId);
  return ReaderChapter(
    id: chapterId,
    seriesId: _seriesId,
    title: 'Chapter ${index + 1}',
    pageCount: _pagesPerChapter,
    sourceId: _sourceId,
    seriesTitle: 'Solo Leveling',
    previousChapterId: index > 0 ? _order[index - 1] : null,
    nextChapterId: index < _order.length - 1 ? _order[index + 1] : null,
    pages: [
      for (var n = 1; n <= _pagesPerChapter; n++)
        ReaderPage(
          id: '$chapterId:$n',
          number: n,
          imageUrl: 'http://example.test$pagePrefix/$chapterId/$n',
          width: 800,
          height: 1200,
        ),
    ],
  );
}

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
/// and over — until the window has released the chapter the route opened at.
Future<void> _readPastTheAnchor(WidgetTester tester) async {
  for (var attempt = 0; attempt < 12; attempt++) {
    if (!_feed(tester).contains(_anchorId)) return;
    final controller = _listController(tester);
    controller.jumpTo(controller.position.maxScrollExtent);
    await _tick(tester);
  }
  fail(
    'the window never slid past $_anchorId — after every slide the feed '
    'held ${_feedChapterIds(tester)}',
  );
}

class _Harness {
  /// Known only once the screen is in the tree; the page prefix is read by
  /// the provider override during the FIRST build, before that.
  late final ProviderContainer container;

  /// Mutable so a test can make the SAME chapter resolve to different bytes.
  String pagePrefix = '/pages';
}

Future<_Harness> _openReadAll(WidgetTester tester) async {
  SharedPreferences.setMockInitialValues(testPrefsDefaults());
  final prefs = await SharedPreferences.getInstance();

  await tester.binding.setSurfaceSize(const Size(430, 932));
  addTearDown(() => tester.binding.setSurfaceSize(null));

  final harness = _Harness();
  await tester.pumpWidget(
    ProviderScope(
      overrides: [
        sharedPrefsProvider.overrideWithValue(prefs),
        apiBaseUrlOverride('http://example.test'),
        // No `(user, profile)` scope: no on-device store, and no download
        // queue for the eager next-chapter prefetch to reach.
        downloadsStoreProvider.overrideWithValue(null),
        sourceReaderPayloadProvider.overrideWith((ref, key) async {
          ref.watch(_payloadDependencyBump);
          return _chapterFor(key.chapterId, pagePrefix: harness.pagePrefix);
        }),
        seriesReadingOrderProvider((sourceId: _sourceId, seriesId: _seriesId))
            .overrideWith((ref) async => _order),
      ],
      child: const MaterialApp(
        home: SourceReaderScreen(
          sourceId: _sourceId,
          seriesId: _seriesId,
          chapterId: _anchorId,
          readAll: true,
        ),
      ),
    ),
  );
  harness.container =
      ProviderScope.containerOf(tester.element(find.byType(SourceReaderScreen)));
  await _tick(tester);

  expect(
    find.byType(ReaderContent),
    findsOneWidget,
    reason: 'the reader should have painted before the test drives it',
  );
  return harness;
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('the source reader keeps a Read-all window that slid past its anchor',
      () {
    testWidgets('the slide itself does not start the feed over',
        (tester) async {
      await _openReadAll(tester);
      await _readPastTheAnchor(tester);

      final chaptersAfterSlide = _feedChapterIds(tester);
      final offsetAfterSlide = _listController(tester).offset;
      expect(chaptersAfterSlide, isNot(contains(_anchorId)));
      expect(chaptersAfterSlide.length, kMaxFeedChapters);

      // The slide notifies, the screen rebuilds, and the rebuild used to be
      // where the window was thrown away. Give it every chance to.
      await _tick(tester, 12);

      expect(
        _feedChapterIds(tester),
        chaptersAfterSlide,
        reason: 'a rebuild after the slide must not collapse the window onto '
            'the chapter the route opened at',
      );
      expect(_listController(tester).offset, offsetAfterSlide);
    });

    testWidgets('an equivalent re-emission of the anchor moves nothing',
        (tester) async {
      final harness = await _openReadAll(tester);
      await _readPastTheAnchor(tester);

      final chaptersBefore = _feedChapterIds(tester);
      final offsetBefore = _listController(tester).offset;

      harness.container.invalidate(sourceReaderChapterProvider(_keyFor(_anchorId)));
      await _tick(tester);

      expect(_feedChapterIds(tester), chaptersBefore);
      expect(_listController(tester).offset, offsetBefore);
    });

    testWidgets('a genuinely different anchor still reaches a window that holds it',
        (tester) async {
      final harness = await _openReadAll(tester);
      // Two chapters in: the anchor is still on screen, so a change to it has
      // somewhere to land.
      for (var attempt = 0; attempt < 12; attempt++) {
        if (_feed(tester).chapters.length >= 2) break;
        final controller = _listController(tester);
        controller.jumpTo(controller.position.maxScrollExtent);
        await _tick(tester);
      }
      final chaptersBefore = _feedChapterIds(tester);
      expect(chaptersBefore, contains(_anchorId));
      expect(chaptersBefore.length, greaterThan(1));

      harness.pagePrefix = '/elsewhere';
      harness.container
        ..invalidate(sourceReaderPayloadProvider(_keyFor(_anchorId)))
        ..invalidate(sourceReaderChapterProvider(_keyFor(_anchorId)));
      await _tick(tester);

      expect(
        _feedChapterIds(tester),
        chaptersBefore,
        reason: 'a changed chapter is folded in, not started over from',
      );
      final anchor = _feed(tester)
          .chapters
          .firstWhere((chapter) => chapter.id == _anchorId);
      expect(anchor.pages.first.imageUrl, contains('/elsewhere/'));
    });

    testWidgets('a dependency-driven reload of the anchor keeps feed and offset',
        (tester) async {
      final harness = await _openReadAll(tester);
      await _readPastTheAnchor(tester);

      final chaptersBefore = _feedChapterIds(tester);
      final offsetBefore = _listController(tester).offset;
      expect(chaptersBefore, isNot(contains(_anchorId)));

      // NOT an invalidate: a dependency of sourceReaderChapterProvider
      // changes, so Riverpod re-runs it as a reload — an AsyncLoading that
      // still carries the old value, which `when` does not skip by default.
      // The screen used to fall back to the skeleton, unmounting the reader,
      // and rebuild it from the route's chapter when the data landed again.
      harness.container.read(_payloadDependencyBump.notifier).state++;
      await _tick(tester);

      expect(
        find.byType(ReaderContent),
        findsOneWidget,
        reason: 'the reader must never drop to the skeleton mid-read',
      );
      expect(_feedChapterIds(tester), chaptersBefore);
      expect(_listController(tester).offset, offsetBefore);
    });

    testWidgets('a different chapter in the route is a different read',
        (tester) async {
      await _openReadAll(tester);
      await _readPastTheAnchor(tester);
      expect(_feedChapterIds(tester), isNot(contains(_anchorId)));

      // The edge prompts `go` to a sibling route and the router hands this
      // same element the new chapter. Keeping the feed here would be the
      // opposite bug: a reader who asked for chapter 6 shown chapter 4's run.
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            sharedPrefsProvider.overrideWithValue(
              await SharedPreferences.getInstance(),
            ),
            apiBaseUrlOverride('http://example.test'),
            downloadsStoreProvider.overrideWithValue(null),
            sourceReaderPayloadProvider.overrideWith(
              (ref, key) async => _chapterFor(key.chapterId),
            ),
            seriesReadingOrderProvider(
              (sourceId: _sourceId, seriesId: _seriesId),
            ).overrideWith((ref) async => _order),
          ],
          child: const MaterialApp(
            home: SourceReaderScreen(
              sourceId: _sourceId,
              seriesId: _seriesId,
              chapterId: 'ch-6',
              readAll: true,
            ),
          ),
        ),
      );
      await _tick(tester);

      // Opening mid-series is allowed to pull in the chapter behind the new
      // anchor (the backward seam), so the feed is built AROUND ch-6 rather
      // than starting at it. What must not be there is any of the old run.
      final chapters = _feedChapterIds(tester);
      expect(chapters, contains('ch-6'));
      expect(chapters, isNot(contains('ch-2')));
      expect(chapters, isNot(contains('ch-3')));
      expect(chapters, isNot(contains('ch-4')));
    });
  });
}
