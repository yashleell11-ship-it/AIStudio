import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/features/reader/models/reader_chapter.dart';
import 'package:manhwamaniacs/features/reader/models/reader_feed.dart';
import 'package:manhwamaniacs/features/reader/models/reader_page.dart';
import 'package:manhwamaniacs/features/reader/utils/reader_feed_controller.dart';
import 'package:manhwamaniacs/features/reader/widgets/chapter_seam.dart';
import 'package:manhwamaniacs/features/reader/widgets/reader_content.dart';
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
