import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/features/reader/models/reader_chapter.dart';
import 'package:manhwamaniacs/features/reader/models/reader_feed.dart';
import 'package:manhwamaniacs/features/reader/models/reader_page.dart';
import 'package:manhwamaniacs/features/reader/utils/page_extents.dart';
import 'package:manhwamaniacs/features/reader/utils/reader_feed_controller.dart';
import 'package:manhwamaniacs/features/reader/widgets/chapter_seam.dart';
import 'package:manhwamaniacs/features/reader/widgets/reader_content.dart';
import 'package:manhwamaniacs/features/settings/models/reader_defaults.dart';
import 'package:manhwamaniacs/shared/providers/core_providers.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// The seamless chapter boundary (spec R1), in the owner's words: "i want to
/// view the chap 1 last and chap 2 starting not like i go to chapter 2
/// directly".
///
/// The claim under test is that there is no boundary in the widget tree at
/// all: two chapters are one scrollable list, the seam is a caption passed on
/// the way through, and crossing it changes nothing except which chapter
/// progress is filed under.

ReaderChapter _chapter(String id, {int pages = 4, String? title}) =>
    ReaderChapter(
      id: id,
      seriesId: 'series',
      title: title ?? 'Chapter $id',
      pageCount: pages,
      pages: [
        for (var n = 1; n <= pages; n++)
          ReaderPage(
            id: '$id:$n',
            number: n,
            imageUrl: 'http://example.test/$id/$n',
            width: 800,
            height: 2400,
          ),
      ],
    );

/// Pages with no declared size — the ordinary case for most sources, and the
/// only one where a decode can still change a page's height mid-session.
ReaderChapter _unsizedChapter(String id, {int pages = 6}) => ReaderChapter(
      id: id,
      seriesId: 'series',
      title: 'Chapter $id',
      pageCount: pages,
      pages: [
        for (var n = 1; n <= pages; n++)
          ReaderPage(
            id: '$id:$n',
            number: n,
            imageUrl: 'http://example.test/$id/$n',
          ),
      ],
    );

/// The geometry the reader itself lays out with, seam dividers included — the
/// dividers are the point, so a helper that omitted them would agree with the
/// bug rather than with the reader.
ReaderPageMetrics _metricsWithSeams(
  WidgetTester tester,
  ReaderPageExtents extents,
  Map<int, double> seams,
) {
  final viewport = MediaQuery.sizeOf(tester.element(find.byType(ListView)));
  return ReaderPageMetrics.of(
    extents,
    direction: ReadingDirection.vertical,
    fitMode: ReaderFitMode.width,
    viewportWidth: viewport.width,
    viewportHeight: viewport.height,
    leadingInsets: seams,
  );
}

Future<SharedPreferences> _freshPrefs() async {
  SharedPreferences.setMockInitialValues({});
  return SharedPreferences.getInstance();
}

Widget _wrap(SharedPreferences prefs, Widget child) => ProviderScope(
      overrides: [sharedPrefsProvider.overrideWithValue(prefs)],
      child: MaterialApp(home: child),
    );

ScrollController _listController(WidgetTester tester) =>
    tester.widget<ListView>(find.byType(ListView)).controller!;

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('the seam in the page list', () {
    testWidgets('two chapters are one continuous list, not two screens',
        (tester) async {
      final prefs = await _freshPrefs();
      await tester.binding.setSurfaceSize(const Size(430, 932));
      addTearDown(() => tester.binding.setSurfaceSize(null));

      await tester.pumpWidget(
        _wrap(
          prefs,
          ReaderContent(
            feed: ReaderFeed.of([_chapter('1'), _chapter('2')]),
            scrollStorageKey: '1',
            onBack: () {},
            onOpenSeries: () {},
          ),
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      // One list, one scroll position, both chapters' pages inside it.
      expect(find.byType(ListView), findsOneWidget);
      final controller = _listController(tester);
      // Eight pages of 2400px are far taller than the viewport: the second
      // chapter is genuinely further down the same scroll, not elsewhere.
      expect(controller.position.maxScrollExtent, greaterThan(932));
    });

    testWidgets('the divider names the chapter being entered, and only that',
        (tester) async {
      final prefs = await _freshPrefs();
      await tester.binding.setSurfaceSize(const Size(430, 932));
      addTearDown(() => tester.binding.setSurfaceSize(null));

      await tester.pumpWidget(
        _wrap(
          prefs,
          ReaderContent(
            feed: ReaderFeed.of([
              _chapter('1', title: 'The Weakest Hunter'),
              _chapter('2', title: 'Awakening'),
            ]),
            scrollStorageKey: '1',
            onBack: () {},
            onOpenSeries: () {},
          ),
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      // Scroll to the boundary. The seam belongs to chapter 2's first page,
      // so it only exists once that page is built.
      _listController(tester).jumpTo(
        _listController(tester).position.maxScrollExtent / 2,
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      expect(find.byType(ChapterSeam), findsOneWidget);
      expect(
        tester.widget<ChapterSeam>(find.byType(ChapterSeam)).title,
        'Awakening',
        reason: 'the divider names where you are going, not where you were',
      );
    });

    testWidgets('a single-chapter feed has no divider at all', (tester) async {
      final prefs = await _freshPrefs();
      await tester.binding.setSurfaceSize(const Size(430, 932));
      addTearDown(() => tester.binding.setSurfaceSize(null));

      await tester.pumpWidget(
        _wrap(
          prefs,
          ReaderContent(
            feed: ReaderFeed.single(_chapter('1')),
            scrollStorageKey: '1',
            onBack: () {},
            onOpenSeries: () {},
          ),
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      expect(find.byType(ChapterSeam), findsNothing);
    });

    testWidgets('the counter and the title follow the chapter under the reader',
        (tester) async {
      final prefs = await _freshPrefs();
      await tester.binding.setSurfaceSize(const Size(430, 932));
      addTearDown(() => tester.binding.setSurfaceSize(null));

      await tester.pumpWidget(
        _wrap(
          prefs,
          ReaderContent(
            feed: ReaderFeed.of([
              _chapter('1', title: 'The Weakest Hunter'),
              _chapter('2', title: 'Awakening'),
            ]),
            scrollStorageKey: '1',
            onBack: () {},
            onOpenSeries: () {},
          ),
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      expect(find.text('The Weakest Hunter'), findsOneWidget);
      // "Page 1 / 4" — of the chapter, never of the eight-page feed.
      expect(find.textContaining('/ 4'), findsOneWidget);

      final controller = _listController(tester);
      controller.jumpTo(controller.position.maxScrollExtent);
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));

      expect(find.text('Awakening'), findsOneWidget);
      expect(find.text('The Weakest Hunter'), findsNothing);
    });

    testWidgets('progress is filed against the chapter the page belongs to',
        (tester) async {
      final prefs = await _freshPrefs();
      await tester.binding.setSurfaceSize(const Size(430, 932));
      addTearDown(() => tester.binding.setSurfaceSize(null));

      final saved = <(String chapterId, int page)>[];

      await tester.pumpWidget(
        _wrap(
          prefs,
          ReaderContent(
            feed: ReaderFeed.of([_chapter('1'), _chapter('2')]),
            scrollStorageKey: '1',
            onSaveProgress: (chapter, page) async {
              saved.add((chapter.id, page));
            },
            onBack: () {},
            onOpenSeries: () {},
          ),
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      final controller = _listController(tester);
      controller.jumpTo(controller.position.maxScrollExtent);
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 600));

      expect(saved, isNotEmpty);
      // The load-bearing assertion of the whole slice: reading into the
      // second chapter records the SECOND chapter, with a page number local
      // to it — not page 8 of a feed nobody will ever open again.
      expect(saved.last.$1, '2');
      expect(saved.last.$2, lessThanOrEqualTo(4));
    });

    testWidgets('the far end of the feed asks for the next chapter early',
        (tester) async {
      final prefs = await _freshPrefs();
      await tester.binding.setSurfaceSize(const Size(430, 932));
      addTearDown(() => tester.binding.setSurfaceSize(null));

      var forward = 0;
      var backward = 0;

      await tester.pumpWidget(
        _wrap(
          prefs,
          ReaderContent(
            feed: ReaderFeed.single(_chapter('1', pages: 12)),
            scrollStorageKey: '1',
            onReachedFeedEnd: () async => forward++,
            onReachedFeedStart: () async => backward++,
            onBack: () {},
            onOpenSeries: () {},
          ),
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      // Opening at the top is within reach of the START of the feed, so the
      // previous chapter is asked for immediately — a boundary you can only
      // cross one way is a trap.
      expect(backward, greaterThan(0));
      expect(forward, 0, reason: 'twelve pages away, nothing to ask for yet');

      final controller = _listController(tester);
      controller.jumpTo(controller.position.maxScrollExtent);
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      expect(forward, greaterThan(0));
    });

    testWidgets('a window slide leaves the reader on the page they were on',
        (tester) async {
      final prefs = await _freshPrefs();
      await tester.binding.setSurfaceSize(const Size(430, 932));
      addTearDown(() => tester.binding.setSurfaceSize(null));

      final saved = <(String, int)>[];
      Widget reader(ReaderFeed feed) => _wrap(
            prefs,
            ReaderContent(
              feed: feed,
              scrollStorageKey: '1',
              onSaveProgress: (chapter, page) async {
                saved.add((chapter.id, page));
              },
              onBack: () {},
              onOpenSeries: () {},
            ),
          );

      await tester.pumpWidget(
        reader(ReaderFeed.of([_chapter('1'), _chapter('2'), _chapter('3')])),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      // Park in the middle chapter — the one that survives the slide.
      final controller = _listController(tester);
      controller.jumpTo(controller.position.maxScrollExtent / 2);
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 600));
      final where = saved.last;
      expect(where.$1, '2', reason: 'the test has to start inside chapter 2');

      // Read-all's window moves on: chapter 1 released, chapter 4 appended, in
      // one assignment. The chapter count is three before and three after —
      // which is exactly why this used to fall through to a wholesale rebuild
      // and drop the reader somewhere else entirely.
      await tester.pumpWidget(
        reader(ReaderFeed.of([_chapter('2'), _chapter('3'), _chapter('4')])),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 600));

      // A correction deliberately notifies nobody, so nudge the position to
      // make the reader say where it thinks it is.
      controller.jumpTo(controller.offset + 1);
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 600));

      expect(
        saved.last,
        where,
        reason: 'the page under the thumb must not move when the window does',
      );
    });

    /// The reported bug, in the owner's words: "while reading the manhwa in
    /// all together after 2-3 chapter it sends me back to 2-3 back i have to
    /// get back to position again and again".
    ///
    /// Scrolling back up arms the backward seam, and the window answers by
    /// prepending a chapter and releasing the tail — three chapters before and
    /// three after, exactly like the forward slide above but released from the
    /// other end. Nothing in the reader had ever changed a mounted feed to
    /// another multi-chapter feed, so this shape had no coverage at all and
    /// shipped uncorrected.
    testWidgets('a window slide BACKWARD leaves the reader where they were',
        (tester) async {
      final prefs = await _freshPrefs();
      await tester.binding.setSurfaceSize(const Size(430, 932));
      addTearDown(() => tester.binding.setSurfaceSize(null));

      final saved = <(String, int)>[];
      Widget reader(ReaderFeed feed) => _wrap(
            prefs,
            ReaderContent(
              feed: feed,
              scrollStorageKey: '1',
              onSaveProgress: (chapter, page) async {
                saved.add((chapter.id, page));
              },
              onBack: () {},
              onOpenSeries: () {},
            ),
          );

      await tester.pumpWidget(
        reader(ReaderFeed.of([_chapter('1'), _chapter('2'), _chapter('3')])),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      final controller = _listController(tester);
      controller.jumpTo(controller.position.maxScrollExtent / 2);
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 600));
      final where = saved.last;
      expect(where.$1, '2', reason: 'the test has to start inside chapter 2');

      // Chapter 0 prepended, chapter 3 released, one assignment. An
      // uncorrected offset here puts a whole chapter above the viewport and
      // sends the reader back by exactly its height — which is the only path
      // in the reader that produces a backwards jump of chapter magnitude.
      await tester.pumpWidget(
        reader(ReaderFeed.of([_chapter('0'), _chapter('1'), _chapter('2')])),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 600));

      // A correction deliberately notifies nobody, so nudge the position to
      // make the reader say where it thinks it is.
      controller.jumpTo(controller.offset + 1);
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 600));

      expect(
        saved.last,
        where,
        reason: 'a chapter arriving ABOVE the viewport must not move the reader',
      );
    });

    /// The same slide again, with the geometry handed in from outside.
    ///
    /// Supplying [ReaderContent.pageExtents] is what every other extents test
    /// does, and it flips the guard on the wholesale-rebuild fallback — so an
    /// injected-extents reader leaves an unrecognised feed change by a
    /// different door than an ordinary one. Both doors have to be shut.
    testWidgets('the backward slide holds with the geometry supplied too',
        (tester) async {
      final prefs = await _freshPrefs();
      await tester.binding.setSurfaceSize(const Size(430, 932));
      addTearDown(() => tester.binding.setSurfaceSize(null));

      final opening =
          ReaderFeed.of([_chapter('1'), _chapter('2'), _chapter('3')]);
      final extents = ReaderPageExtents(opening.pages);
      addTearDown(extents.dispose);

      final saved = <(String, int)>[];
      Widget reader(ReaderFeed feed) => _wrap(
            prefs,
            ReaderContent(
              feed: feed,
              scrollStorageKey: '1',
              pageExtents: extents,
              onSaveProgress: (chapter, page) async {
                saved.add((chapter.id, page));
              },
              onBack: () {},
              onOpenSeries: () {},
            ),
          );

      await tester.pumpWidget(reader(opening));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      final controller = _listController(tester);
      controller.jumpTo(controller.position.maxScrollExtent / 2);
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 600));
      final where = saved.last;
      expect(where.$1, '2', reason: 'the test has to start inside chapter 2');

      await tester.pumpWidget(
        reader(ReaderFeed.of([_chapter('0'), _chapter('1'), _chapter('2')])),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 600));

      controller.jumpTo(controller.offset + 1);
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 600));

      expect(saved.last, where);
      // The extents have to describe the new feed page for page, or every
      // height below the seam belongs to a different page than the one it is
      // laid out for.
      expect(extents.length, 12);
    });

    /// A seam page is the one page whose extent and whose scroll offset differ
    /// by the divider above it. Correcting its growth against the extent
    /// WITHOUT the divider left the reader 96px further up the strip every time
    /// a chapter's first page resolved behind them — page-scale drift rather
    /// than chapter-scale, but the same class of error and it accumulates once
    /// per seam crossed.
    testWidgets('a seam page resolving above the viewport corrects in full',
        (tester) async {
      final prefs = await _freshPrefs();
      await tester.binding.setSurfaceSize(const Size(430, 932));
      addTearDown(() => tester.binding.setSurfaceSize(null));

      final feed = ReaderFeed.of([_unsizedChapter('1'), _unsizedChapter('2')]);
      final extents = ReaderPageExtents(feed.pages);
      addTearDown(extents.dispose);

      await tester.pumpWidget(
        _wrap(
          prefs,
          ReaderContent(
            feed: feed,
            scrollStorageKey: '1',
            pageExtents: extents,
            onBack: () {},
            onOpenSeries: () {},
          ),
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      // Chapter 2's first page — the only page in this feed carrying a divider.
      const seam = 6;
      final metrics = _metricsWithSeams(tester, extents, {
        seam: kChapterSeamExtent,
      });
      expect(
        metrics.extentAt(seam) -
            metrics.extentForRatio(metrics.ratioAt(seam)),
        kChapterSeamExtent,
      );

      final controller = _listController(tester);
      // Two pages past the seam, so it is entirely above the viewport and the
      // whole of its growth pushes the visible page down.
      controller.jumpTo(metrics.offsetToPage(seam + 3));
      await tester.pump();
      final before = controller.offset;

      // It decodes as a tall webtoon strip, many times the 2/3 fallback.
      final growth = metrics.extentForRatio(900 / 16000) -
          metrics.extentForRatio(metrics.ratioAt(seam));
      expect(
        growth,
        greaterThan(kChapterSeamExtent * 10),
        reason: 'the fixture has to grow far more than the divider is tall',
      );

      extents.submitMeasuredSize(seam, pixelWidth: 900, pixelHeight: 16000);
      await tester.pump();
      await tester.pump();

      // The divider did not change size, so it is in both the before and the
      // after and cancels out. Counting it on one side only left the reader
      // exactly [kChapterSeamExtent] short.
      expect(controller.offset, moreOrLessEquals(before + growth, epsilon: 1));
    });
  });

  group('ReaderFeedController', () {
    ReaderFeedController build({
      List<String>? order,
      String? next,
      String? prev,
      Future<ReaderChapter?> Function(String)? loader,
      int maxChapters = kMaxFeedChapters,
    }) =>
        ReaderFeedController(
          anchor: _chapter('2'),
          prev: prev,
          next: next,
          order: order,
          loadChapter: loader ?? (id) async => _chapter(id),
          maxChapters: maxChapters,
        );

    test('extends forward into the chapter the anchor said comes next',
        () async {
      final controller = build(next: '3');
      addTearDown(controller.dispose);

      await controller.extendForward();

      expect(controller.feed.chapters.map((c) => c.id), ['2', '3']);
    });

    test('extends backward too — the seam is crossable both ways', () async {
      final controller = build(prev: '1');
      addTearDown(controller.dispose);

      await controller.extendBackward();

      expect(controller.feed.chapters.map((c) => c.id), ['1', '2']);
    });

    test('the end of the series is a no-op, not an error', () async {
      final controller = build();
      addTearDown(controller.dispose);

      await controller.extendForward();
      await controller.extendBackward();

      expect(controller.feed.chapters.map((c) => c.id), ['2']);
    });

    test('a chapter that will not load leaves the feed exactly as it was',
        () async {
      final controller = build(next: '3', loader: (_) async => null);
      addTearDown(controller.dispose);

      await controller.extendForward();

      // The edge prompt stays as the way across; nothing is broken.
      expect(controller.feed.chapters.map((c) => c.id), ['2']);
    });

    test('with the series order in hand it needs no round trip to navigate',
        () async {
      final controller = build(order: ['1', '2', '3', '4']);
      addTearDown(controller.dispose);

      await controller.extendForward();
      await controller.extendBackward();

      expect(controller.feed.chapters.map((c) => c.id), ['1', '2', '3']);
    });

    test('the window slides — it never grows past its bound', () async {
      final controller = build(order: ['1', '2', '3', '4', '5', '6']);
      addTearDown(controller.dispose);

      for (var i = 0; i < 5; i++) {
        await controller.extendForward();
      }

      // Read-all is not a longer feed: 300 chapters cost the same as 3.
      expect(controller.feed.chapters, hasLength(3));
      expect(controller.feed.chapters.map((c) => c.id), ['4', '5', '6']);
    });

    test('sliding back releases from the other end', () async {
      final controller = build(
        order: ['1', '2', '3', '4'],
        maxChapters: 2,
      );
      addTearDown(controller.dispose);

      await controller.extendForward(); // [2, 3]
      expect(controller.feed.chapters.map((c) => c.id), ['2', '3']);

      await controller.extendBackward(); // [1, 2] — 3 released behind
      expect(controller.feed.chapters.map((c) => c.id), ['1', '2']);
    });

    test('neighbours learned late still open the seam', () async {
      final controller = build();
      addTearDown(controller.dispose);

      // Nothing known yet (a downloaded chapter opened from disk), so nothing
      // to extend into.
      await controller.extendForward();
      expect(controller.feed.chapters, hasLength(1));

      // The manifest lands out of band (spec R3) and the seam opens.
      controller.noteNeighbours('2', next: '3');
      await controller.extendForward();
      expect(controller.feed.chapters.map((c) => c.id), ['2', '3']);
    });

    test('a chapter in hand crosses the seam without waiting on neighbours',
        () async {
      final neighbours = Completer<({String? prev, String? next})>();
      final controller = ReaderFeedController(
        anchor: _chapter('2'),
        next: '3',
        loadChapter: (id) async => _chapter(id),
        neighboursOf: (_) => neighbours.future,
      );
      addTearDown(controller.dispose);

      await controller.extendForward();

      // The pages are in hand — from disk, on a downloaded chapter — and that
      // is the whole precondition for showing them (spec R3). What lies beyond
      // chapter 3 is learned behind the reader, not in front of them.
      expect(controller.feed.chapters.map((c) => c.id), ['2', '3']);
      expect(controller.isExtending, isFalse);

      neighbours.complete((prev: '2', next: '4'));
      await Future<void>.delayed(Duration.zero);

      await controller.extendForward();
      expect(controller.feed.chapters.map((c) => c.id), ['2', '3', '4']);
    });

    test('a backward fetch in flight does not hold up the forward seam',
        () async {
      final gate = Completer<void>();
      final controller = ReaderFeedController(
        anchor: _chapter('2'),
        order: ['1', '2', '3'],
        loadChapter: (id) async {
          if (id == '1') await gate.future;
          return _chapter(id);
        },
      );
      addTearDown(controller.dispose);

      // Entering Read-all mid-series asks for the chapter BEHIND the reader on
      // its opening frames. Forward is the direction the mode is about.
      final backward = controller.extendBackward();
      await controller.extendForward();
      expect(controller.feed.chapters.map((c) => c.id), ['2', '3']);

      gate.complete();
      await backward;
      expect(controller.feed.chapters.map((c) => c.id), ['1', '2', '3']);
    });

    test('a source that refuses is not asked again on the next scroll frame',
        () async {
      var attempts = 0;
      var now = DateTime(2026);
      final controller = ReaderFeedController(
        anchor: _chapter('2'),
        order: ['2', '3'],
        clock: () => now,
        loadChapter: (_) async {
          attempts++;
          return null;
        },
      );
      addTearDown(controller.dispose);

      await controller.extendForward();
      expect(attempts, 1);

      // At the end of the feed the reader sits where overscroll bounces keep
      // firing scroll notifications, and every one of them re-arms the trigger.
      for (var i = 0; i < 20; i++) {
        await controller.extendForward();
      }
      expect(attempts, 1, reason: 'a 429 must not be answered with twenty more');

      now = now.add(const Duration(seconds: 3));
      await controller.extendForward();
      expect(attempts, 2, reason: 'backed off, not given up');
    });

    test('the way out of a run points past the FEED, not past the anchor',
        () async {
      final controller = build(order: ['1', '2', '3', '4', '5', '6']);
      addTearDown(controller.dispose);

      expect(controller.previousBeforeFeed, '1');
      expect(controller.nextBeyondFeed, '3');

      for (var i = 0; i < 5; i++) {
        await controller.extendForward();
      }

      // The window has slid to [4, 5, 6]. A run that dead-ends here must not
      // offer the anchor's neighbour — that is thirty minutes backwards.
      expect(controller.feed.chapters.map((c) => c.id), ['4', '5', '6']);
      expect(controller.previousBeforeFeed, '3');
      expect(controller.nextBeyondFeed, isNull);
    });

    test('two extensions racing add one chapter, not two', () async {
      final gate = Completer<void>();
      final controller = ReaderFeedController(
        anchor: _chapter('2'),
        next: '3',
        loadChapter: (id) async {
          await gate.future;
          return _chapter(id);
        },
      );
      addTearDown(controller.dispose);

      final first = controller.extendForward();
      final second = controller.extendForward();
      gate.complete();
      await Future.wait([first, second]);

      expect(controller.feed.chapters, hasLength(2));
    });
  });
}
