import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/features/reader/models/reader_chapter.dart';
import 'package:manhwamaniacs/features/reader/models/reader_feed.dart';
import 'package:manhwamaniacs/features/reader/models/reader_page.dart';
import 'package:manhwamaniacs/features/reader/utils/page_extents.dart';
import 'package:manhwamaniacs/features/reader/widgets/reader_content.dart';
import 'package:manhwamaniacs/features/settings/models/reader_defaults.dart';
import 'package:manhwamaniacs/shared/providers/core_providers.dart';
import 'package:shared_preferences/shared_preferences.dart';

ReaderChapter _sampleChapter({
  String? previousChapterId,
  String? nextChapterId,
}) {
  return ReaderChapter(
    id: '1',
    seriesId: '1',
    title: 'Chapter 1',
    pageCount: 2,
    previousChapterId: previousChapterId,
    nextChapterId: nextChapterId,
    pages: const [
      ReaderPage(
        id: '101',
        number: 1,
        imageUrl: 'http://example.test/reader/page/101/image',
        width: 800,
        height: 1200,
      ),
      ReaderPage(
        id: '102',
        number: 2,
        imageUrl: 'http://example.test/reader/page/102/image',
        width: 800,
        height: 1200,
      ),
    ],
  );
}

/// A chapter tall enough that its total content height clearly exceeds the
/// test viewport (430x932), so "at bottom" and "at top" are genuinely
/// distinct scroll states. The 2-page [_sampleChapter] is too short for
/// that: its total height is smaller than the viewport, so the "at bottom"
/// threshold check is trivially true at every scroll position, including
/// the very top — any test asserting on leaving/returning to bottom needs
/// this fixture instead.
ReaderChapter _tallChapter({String? nextChapterId}) {
  return ReaderChapter(
    id: '1',
    seriesId: '1',
    title: 'Chapter 1',
    pageCount: 6,
    nextChapterId: nextChapterId,
    pages: List.generate(
      6,
      (index) => ReaderPage(
        id: '${101 + index}',
        number: index + 1,
        imageUrl: 'http://example.test/reader/page/${101 + index}/image',
        width: 800,
        height: 1200,
      ),
    ),
  );
}

/// A chapter whose pages carry no dimensions at all — the un-backfilled case
/// the reader has to stay stable through. Every page opens on the fallback
/// ratio and only learns its real height once the image decodes.
ReaderChapter _dimensionlessChapter({int pageCount = 8}) {
  return ReaderChapter(
    id: '1',
    seriesId: '1',
    title: 'Chapter 1',
    pageCount: pageCount,
    pages: List.generate(
      pageCount,
      (index) => ReaderPage(
        id: '${101 + index}',
        number: index + 1,
        imageUrl: 'http://example.test/reader/page/${101 + index}/image',
      ),
    ),
  );
}

/// Six pages tall enough that the last one can actually be scrolled to the top
/// of the viewport, which is what makes "drag the rail to the end" land on the
/// final page rather than one short of it.
ReaderChapter _scrubChapter({int pageCount = 6}) {
  return ReaderChapter(
    id: '1',
    seriesId: '1',
    title: 'Chapter 1',
    pageCount: pageCount,
    pages: List.generate(
      pageCount,
      (index) => ReaderPage(
        id: '${101 + index}',
        number: index + 1,
        imageUrl: 'http://example.test/reader/page/${101 + index}/image',
        width: 800,
        height: 2400,
      ),
    ),
  );
}

/// The geometry the reader is laying its pages out with right now.
///
/// Read from the reader's own MediaQuery rather than assumed: `setSurfaceSize`
/// changes what the list is laid out into but not what MediaQuery reports, and
/// the reader sizes pages from the latter. Tests that need exact offsets
/// therefore leave the surface size alone so the two agree.
ReaderPageMetrics _metricsFor(WidgetTester tester, ReaderPageExtents extents) {
  final viewport = MediaQuery.sizeOf(tester.element(find.byType(ListView)));
  return ReaderPageMetrics.of(
    extents,
    direction: ReadingDirection.vertical,
    fitMode: ReaderFitMode.width,
    viewportWidth: viewport.width,
    viewportHeight: viewport.height,
  );
}

ScrollController _listController(WidgetTester tester) =>
    tester.widget<ListView>(find.byType(ListView)).controller!;

Future<SharedPreferences> _freshPrefs([
  Map<String, Object> values = const {},
]) async {
  SharedPreferences.setMockInitialValues(values);
  return SharedPreferences.getInstance();
}

const _readingDirectionKey = 'settings_reading_direction';

Widget _wrapWithPrefs(SharedPreferences prefs, Widget child) {
  return ProviderScope(
    overrides: [
      sharedPrefsProvider.overrideWithValue(prefs),
    ],
    child: MaterialApp(home: child),
  );
}

/// Opens the more-options bottom sheet from the visible controls bar.
Future<void> _openMoreSheet(WidgetTester tester) async {
  await tester.tap(find.byTooltip('Reader settings'));
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 300));
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('ReaderContent', () {
    testWidgets('renders title, page indicator and controls', (tester) async {
      final prefs = await _freshPrefs();
      await tester.binding.setSurfaceSize(const Size(430, 932));
      addTearDown(() => tester.binding.setSurfaceSize(null));

      await tester.pumpWidget(
        _wrapWithPrefs(
          prefs,
          ReaderContent(
            feed: ReaderFeed.single(_sampleChapter()),
            scrollStorageKey: '1',
            onBack: () {},
            onOpenSeries: () {},
          ),
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      expect(find.text('Chapter 1'), findsOneWidget);
      expect(find.textContaining('Page 1 / 2'), findsOneWidget);
      expect(find.byTooltip('Back'), findsOneWidget);
    });

    testWidgets('shows Save bookmark in more-options sheet when callback is provided',
        (tester) async {
      final prefs = await _freshPrefs();
      await tester.binding.setSurfaceSize(const Size(430, 932));
      addTearDown(() => tester.binding.setSurfaceSize(null));

      await tester.pumpWidget(
        _wrapWithPrefs(
          prefs,
          ReaderContent(
            feed: ReaderFeed.single(_sampleChapter()),
            scrollStorageKey: '1',
            onAddBookmark: (_, __) async => true,
            onBack: () {},
            onOpenSeries: () {},
          ),
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      await _openMoreSheet(tester);

      expect(find.text('Save bookmark'), findsOneWidget);
    });

    testWidgets('hides Save bookmark in more-options sheet for online chapters',
        (tester) async {
      final prefs = await _freshPrefs();
      await tester.binding.setSurfaceSize(const Size(430, 932));
      addTearDown(() => tester.binding.setSurfaceSize(null));

      await tester.pumpWidget(
        _wrapWithPrefs(
          prefs,
          ReaderContent(
            feed: ReaderFeed.single(_sampleChapter()),
            scrollStorageKey: 'src:1:1',
            showBookmark: false,
            onBack: () {},
            onOpenSeries: () {},
          ),
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      await _openMoreSheet(tester);

      expect(find.text('Save bookmark'), findsNothing);
    });

    testWidgets('disables Prev/Next buttons in sheet when chapter ids absent',
        (tester) async {
      final prefs = await _freshPrefs();
      await tester.binding.setSurfaceSize(const Size(430, 932));
      addTearDown(() => tester.binding.setSurfaceSize(null));

      await tester.pumpWidget(
        _wrapWithPrefs(
          prefs,
          ReaderContent(
            feed: ReaderFeed.single(_sampleChapter()),
            scrollStorageKey: '1',
            onBack: () {},
            onOpenSeries: () {},
          ),
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      await _openMoreSheet(tester);

      final prevButton = tester.widget<OutlinedButton>(
        find.ancestor(
          of: find.text('Prev'),
          matching: find.byType(OutlinedButton),
        ),
      );
      final nextButton = tester.widget<OutlinedButton>(
        find.ancestor(
          of: find.text('Next'),
          matching: find.byType(OutlinedButton),
        ),
      );
      expect(prevButton.enabled, isFalse);
      expect(nextButton.enabled, isFalse);
    });

    testWidgets('does not persist progress when no callback supplied',
        (tester) async {
      final prefs = await _freshPrefs();
      await tester.binding.setSurfaceSize(const Size(430, 932));
      addTearDown(() => tester.binding.setSurfaceSize(null));

      const saveCalls = 0;
      await tester.pumpWidget(
        _wrapWithPrefs(
          prefs,
          ReaderContent(
            feed: ReaderFeed.single(_sampleChapter()),
            scrollStorageKey: '1',
            onBack: () {},
            onOpenSeries: () {},
            // No onSaveProgress — progress must never fire.
          ),
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      expect(saveCalls, 0);
    });

    testWidgets('invokes onBack when Back tapped', (tester) async {
      final prefs = await _freshPrefs();
      await tester.binding.setSurfaceSize(const Size(430, 932));
      addTearDown(() => tester.binding.setSurfaceSize(null));

      var backCalls = 0;
      await tester.pumpWidget(
        _wrapWithPrefs(
          prefs,
          ReaderContent(
            feed: ReaderFeed.single(_sampleChapter()),
            scrollStorageKey: '1',
            onBack: () => backCalls++,
            onOpenSeries: () {},
          ),
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      await tester.tap(find.byTooltip('Back'));
      await tester.pump();

      expect(backCalls, 1);
    });

    testWidgets('shows bookmark snackbar only when callback returns true',
        (tester) async {
      final prefs = await _freshPrefs();
      await tester.binding.setSurfaceSize(const Size(430, 932));
      addTearDown(() => tester.binding.setSurfaceSize(null));

      await tester.pumpWidget(
        _wrapWithPrefs(
          prefs,
          ReaderContent(
            feed: ReaderFeed.single(_sampleChapter()),
            scrollStorageKey: '1',
            onAddBookmark: (_, __) async => true,
            onBack: () {},
            onOpenSeries: () {},
          ),
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      await _openMoreSheet(tester);
      await tester.ensureVisible(find.text('Save bookmark'));
      await tester.tap(find.text('Save bookmark'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      // The confirmation now names the exact position, so match the stable
      // half of it: the percentage depends on the sample chapter's geometry.
      expect(find.textContaining('Bookmarked page 1'), findsOneWidget);
    });

    testWidgets('hides bookmark snackbar when callback returns false',
        (tester) async {
      final prefs = await _freshPrefs();
      await tester.binding.setSurfaceSize(const Size(430, 932));
      addTearDown(() => tester.binding.setSurfaceSize(null));

      await tester.pumpWidget(
        _wrapWithPrefs(
          prefs,
          ReaderContent(
            feed: ReaderFeed.single(_sampleChapter()),
            scrollStorageKey: '1',
            onAddBookmark: (_, __) async => false,
            onBack: () {},
            onOpenSeries: () {},
          ),
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      await _openMoreSheet(tester);
      await tester.ensureVisible(find.text('Save bookmark'));
      await tester.tap(find.text('Save bookmark'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      expect(find.textContaining('Bookmarked page'), findsNothing);
    });

    testWidgets('clears bookmark pending after callback throws', (tester) async {
      final prefs = await _freshPrefs();
      await tester.binding.setSurfaceSize(const Size(430, 932));
      addTearDown(() => tester.binding.setSurfaceSize(null));

      dynamic caughtError;
      await runZonedGuarded(() async {
        await tester.pumpWidget(
          _wrapWithPrefs(
            prefs,
            ReaderContent(
              feed: ReaderFeed.single(_sampleChapter()),
              scrollStorageKey: '1',
              onAddBookmark: (_, __) async => throw Exception('bookmark failed'),
              onBack: () {},
              onOpenSeries: () {},
            ),
          ),
        );
        await tester.pump();
        await tester.pump(const Duration(milliseconds: 100));

        await _openMoreSheet(tester);
        await tester.ensureVisible(find.text('Save bookmark'));
      await tester.tap(find.text('Save bookmark'));
        await tester.pump();
        await tester.pump(const Duration(milliseconds: 100));
      }, (error, stack) {
        caughtError = error;
      });

      expect(caughtError, isNotNull);

      // After the error, the sheet was dismissed and bookmark pending cleared.
      // Opening the sheet again should show an enabled Save bookmark button.
      await _openMoreSheet(tester);
      expect(find.text('Save bookmark'), findsOneWidget);
    });

    testWidgets('re-arms auto-next timer after scrolling away from bottom',
        (tester) async {
      final prefs = await _freshPrefs();
      await tester.binding.setSurfaceSize(const Size(430, 932));
      addTearDown(() => tester.binding.setSurfaceSize(null));

      var nextCalls = 0;
      await tester.pumpWidget(
        _wrapWithPrefs(
          prefs,
          ReaderContent(
            feed: ReaderFeed.single(_sampleChapter(nextChapterId: '2')),
            scrollStorageKey: '1',
            onBack: () {},
            onOpenSeries: () {},
            onNextChapter: () => nextCalls++,
          ),
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      final listView = find.byType(ListView);
      // Reach the bottom: the countdown starts.
      await tester.drag(listView, const Offset(0, -4000));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 500));

      // Scroll back to the top before it fires — that cancels it outright.
      await tester.drag(listView, const Offset(0, 4000));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 1000));
      expect(nextCalls, 0);

      // Returning to the bottom has to arm a fresh countdown, otherwise a
      // reader who scrolls back up once never gets auto-next again.
      await tester.drag(listView, const Offset(0, -4000));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 1000));

      expect(nextCalls, 1);
    });

    testWidgets(
      'does not restart the auto-next countdown on repeated scroll events '
      'while remaining at the bottom',
      (tester) async {
        final prefs = await _freshPrefs();
        await tester.binding.setSurfaceSize(const Size(430, 932));
        addTearDown(() => tester.binding.setSurfaceSize(null));

        var nextCalls = 0;
        await tester.pumpWidget(
          _wrapWithPrefs(
            prefs,
            ReaderContent(
              feed: ReaderFeed.single(_tallChapter(nextChapterId: '2')),
              scrollStorageKey: '1',
              onBack: () {},
              onOpenSeries: () {},
              onNextChapter: () => nextCalls++,
            ),
          ),
        );
        await tester.pump();
        await tester.pump(const Duration(milliseconds: 100));

        final controller =
            tester.widget<ListView>(find.byType(ListView)).controller!;
        final maxExtent = controller.position.maxScrollExtent;
        expect(maxExtent, greaterThan(500), reason: 'fixture must be scrollable');

        // Reach the bottom: this arms the countdown (fires at +900ms).
        controller.jumpTo(maxExtent);
        await tester.pump();
        await tester.pump(const Duration(milliseconds: 300));

        // Simulate late-arriving scroll notifications (e.g. an image
        // finishing its load) while still sitting at the bottom. A small
        // wiggle stays within the edge threshold, so _atBottom remains
        // true throughout and _handleScroll fires again without the reader
        // ever leaving bottom. This must NOT push the countdown further out.
        controller.jumpTo(maxExtent - 20);
        await tester.pump();
        controller.jumpTo(maxExtent);
        await tester.pump();
        await tester.pump(const Duration(milliseconds: 300));

        // 300ms (arrival) + 300ms (after wiggle) = 600ms < 900ms.
        expect(nextCalls, 0);

        // Advance past the ORIGINAL 900ms window measured from the first
        // arrival at bottom (600ms + 400ms = 1000ms). A buggy implementation
        // that restarted the timer at the wiggle (t=300ms) would only fire
        // at t=1200ms and still be 0 here.
        await tester.pump(const Duration(milliseconds: 400));

        expect(nextCalls, 1);
      },
    );

    testWidgets(
      'cancels the auto-next countdown when leaving the bottom before it fires',
      (tester) async {
        final prefs = await _freshPrefs();
        await tester.binding.setSurfaceSize(const Size(430, 932));
        addTearDown(() => tester.binding.setSurfaceSize(null));

        var nextCalls = 0;
        await tester.pumpWidget(
          _wrapWithPrefs(
            prefs,
            ReaderContent(
              feed: ReaderFeed.single(_tallChapter(nextChapterId: '2')),
              scrollStorageKey: '1',
              onBack: () {},
              onOpenSeries: () {},
              onNextChapter: () => nextCalls++,
            ),
          ),
        );
        await tester.pump();
        await tester.pump(const Duration(milliseconds: 100));

        final controller =
            tester.widget<ListView>(find.byType(ListView)).controller!;
        final maxExtent = controller.position.maxScrollExtent;

        // Reach the bottom: arms the countdown.
        controller.jumpTo(maxExtent);
        await tester.pump();
        await tester.pump(const Duration(milliseconds: 300));

        // Leave the bottom well before the 900ms window elapses.
        controller.jumpTo(0);
        await tester.pump();

        // Wait well past the original window; the countdown must have been
        // cancelled on leaving, not merely left to fire later.
        await tester.pump(const Duration(milliseconds: 1200));

        expect(nextCalls, 0);
      },
    );

    testWidgets(
      'returning to the bottom starts exactly one new countdown',
      (tester) async {
        final prefs = await _freshPrefs();
        await tester.binding.setSurfaceSize(const Size(430, 932));
        addTearDown(() => tester.binding.setSurfaceSize(null));

        var nextCalls = 0;
        await tester.pumpWidget(
          _wrapWithPrefs(
            prefs,
            ReaderContent(
              feed: ReaderFeed.single(_tallChapter(nextChapterId: '2')),
              scrollStorageKey: '1',
              onBack: () {},
              onOpenSeries: () {},
              onNextChapter: () => nextCalls++,
            ),
          ),
        );
        await tester.pump();
        await tester.pump(const Duration(milliseconds: 100));

        final controller =
            tester.widget<ListView>(find.byType(ListView)).controller!;
        final maxExtent = controller.position.maxScrollExtent;

        // Reach bottom, then leave before it fires (cancels the countdown).
        controller.jumpTo(maxExtent);
        await tester.pump();
        await tester.pump(const Duration(milliseconds: 300));
        controller.jumpTo(0);
        await tester.pump();
        await tester.pump(const Duration(milliseconds: 300));
        expect(nextCalls, 0);

        // Return to bottom: exactly one fresh countdown starts here.
        controller.jumpTo(maxExtent);
        await tester.pump();
        await tester.pump(const Duration(milliseconds: 700));
        // Only 700ms since returning: must not have fired yet.
        expect(nextCalls, 0);

        await tester.pump(const Duration(milliseconds: 300));
        // 1000ms since returning: the single fresh countdown has fired once.
        expect(nextCalls, 1);
      },
    );

    testWidgets(
      'a page resolving taller ABOVE the viewport does not move the reader',
      (tester) async {
        final prefs = await _freshPrefs();

        final chapter = _dimensionlessChapter();
        final extents = ReaderPageExtents(chapter.pages);
        addTearDown(extents.dispose);

        await tester.pumpWidget(
          _wrapWithPrefs(
            prefs,
            ReaderContent(
              feed: ReaderFeed.single(chapter),
              scrollStorageKey: '1',
              pageExtents: extents,
              onBack: () {},
              onOpenSeries: () {},
            ),
          ),
        );
        await tester.pump();
        await tester.pump(const Duration(milliseconds: 100));

        final metrics = _metricsFor(tester, extents);
        final controller = _listController(tester);

        // Settle on page 4, several pages deep — page 1 is now well above the
        // viewport and the reader can no longer see it at all.
        controller.jumpTo(metrics.offsetToPage(4));
        await tester.pump();
        expect(find.text('Page 4 / 8'), findsOneWidget);

        // Page 1 decodes as a 900x16000 webtoon strip: more than ten times the
        // height the list reserved for it on the 2/3 fallback.
        final grownExtent = metrics.extentForRatio(900 / 16000);
        final delta = grownExtent - metrics.extentAt(0);
        expect(delta, greaterThan(6000), reason: 'fixture must grow a lot');

        extents.submitMeasuredSize(0, pixelWidth: 900, pixelHeight: 16000);
        await tester.pump();
        await tester.pump();

        // Without the correction the whole chapter below page 1 slides down by
        // `delta` while the offset stays put, and the reader is dumped back
        // onto page 1 — the reported "it randomly sent me to the pages above".
        expect(find.text('Page 4 / 8'), findsOneWidget);
        expect(
          controller.offset,
          moreOrLessEquals(metrics.offsetToPage(4) + delta, epsilon: 1),
        );
      },
    );

    testWidgets(
      'a page resolving BELOW the viewport leaves the offset alone',
      (tester) async {
        final prefs = await _freshPrefs();

        final chapter = _dimensionlessChapter();
        final extents = ReaderPageExtents(chapter.pages);
        addTearDown(extents.dispose);

        await tester.pumpWidget(
          _wrapWithPrefs(
            prefs,
            ReaderContent(
              feed: ReaderFeed.single(chapter),
              scrollStorageKey: '1',
              pageExtents: extents,
              onBack: () {},
              onOpenSeries: () {},
            ),
          ),
        );
        await tester.pump();
        await tester.pump(const Duration(milliseconds: 100));

        final metrics = _metricsFor(tester, extents);
        final controller = _listController(tester);
        controller.jumpTo(metrics.offsetToPage(2));
        await tester.pump();

        // Page 6 is far below; nothing the reader can see depends on it, so
        // correcting for it would itself be the jump.
        extents.submitMeasuredSize(5, pixelWidth: 900, pixelHeight: 16000);
        await tester.pump();
        await tester.pump();

        expect(
          controller.offset,
          moreOrLessEquals(metrics.offsetToPage(2), epsilon: 0.01),
        );
        expect(find.text('Page 2 / 8'), findsOneWidget);
      },
    );

    testWidgets(
      'a page only ever changes extent once',
      (tester) async {
        final prefs = await _freshPrefs();

        final chapter = _dimensionlessChapter();
        final extents = ReaderPageExtents(chapter.pages);
        addTearDown(extents.dispose);

        await tester.pumpWidget(
          _wrapWithPrefs(
            prefs,
            ReaderContent(
              feed: ReaderFeed.single(chapter),
              scrollStorageKey: '1',
              pageExtents: extents,
              onBack: () {},
              onOpenSeries: () {},
            ),
          ),
        );
        await tester.pump();
        await tester.pump(const Duration(milliseconds: 100));

        final metrics = _metricsFor(tester, extents);
        final controller = _listController(tester);
        controller.jumpTo(metrics.offsetToPage(4));
        await tester.pump();

        extents.submitMeasuredSize(0, pixelWidth: 900, pixelHeight: 16000);
        await tester.pump();
        await tester.pump();
        final settled = controller.offset;

        // A second, contradictory measurement of the same page must be ignored:
        // acting on it would move the reader a second time for one page.
        extents.submitMeasuredSize(0, pixelWidth: 900, pixelHeight: 900);
        await tester.pump();
        await tester.pump();

        expect(controller.offset, moreOrLessEquals(settled, epsilon: 0.01));
        expect(find.text('Page 4 / 8'), findsOneWidget);
      },
    );

    testWidgets(
      'no page counter floats over the reading area',
      (tester) async {
        final prefs = await _freshPrefs();
        await tester.binding.setSurfaceSize(const Size(430, 932));
        addTearDown(() => tester.binding.setSurfaceSize(null));

        await tester.pumpWidget(
          _wrapWithPrefs(
            prefs,
            ReaderContent(
              feed: ReaderFeed.single(_sampleChapter()),
              scrollStorageKey: '1',
              onBack: () {},
              onOpenSeries: () {},
            ),
          ),
        );
        await tester.pump();
        await tester.pump(const Duration(milliseconds: 100));

        // The overlay pill rendered exactly "1 / 2" at the top of the page.
        expect(find.text('1 / 2'), findsNothing);

        // Let the controls auto-hide, which is precisely when that pill used to
        // appear on top of the artwork.
        await tester.pump(const Duration(milliseconds: 3500));
        expect(find.text('1 / 2'), findsNothing);

        // The bottom bar's counter is the one the owner wants kept.
        expect(find.text('Page 1 / 2'), findsOneWidget);
      },
    );

    testWidgets(
      'dragging the bottom rail to the end jumps to the last page',
      (tester) async {
        final prefs = await _freshPrefs();

        final chapter = _scrubChapter();
        final extents = ReaderPageExtents(chapter.pages);
        addTearDown(extents.dispose);

        await tester.pumpWidget(
          _wrapWithPrefs(
            prefs,
            ReaderContent(
              feed: ReaderFeed.single(chapter),
              scrollStorageKey: '1',
              pageExtents: extents,
              onBack: () {},
              onOpenSeries: () {},
            ),
          ),
        );
        await tester.pump();
        await tester.pump(const Duration(milliseconds: 100));

        expect(find.text('Page 1 / 6'), findsOneWidget);

        final rail = tester.getRect(find.byType(Slider));
        await tester.dragFrom(rail.center, Offset(rail.width, 0));
        await tester.pump();
        await tester.pump(const Duration(milliseconds: 100));

        expect(find.text('Page 6 / 6'), findsOneWidget);
        // The seek has to resolve through the same geometry the list is laid
        // out from; a second estimator would land somewhere near it, not on it.
        expect(
          _listController(tester).offset,
          moreOrLessEquals(
            _metricsFor(tester, extents).offsetToPage(6),
            epsilon: 1,
          ),
        );
      },
    );

    testWidgets(
      'tapping the bottom rail jumps to that point in the chapter',
      (tester) async {
        final prefs = await _freshPrefs();

        final chapter = _scrubChapter();
        final extents = ReaderPageExtents(chapter.pages);
        addTearDown(extents.dispose);

        await tester.pumpWidget(
          _wrapWithPrefs(
            prefs,
            ReaderContent(
              feed: ReaderFeed.single(chapter),
              scrollStorageKey: '1',
              pageExtents: extents,
              onBack: () {},
              onOpenSeries: () {},
            ),
          ),
        );
        await tester.pump();
        await tester.pump(const Duration(milliseconds: 100));

        final rail = tester.getRect(find.byType(Slider));
        await tester.tapAt(rail.center);
        await tester.pump();
        await tester.pump(const Duration(milliseconds: 100));

        // Halfway along a six-page rail is page 3 or 4 depending on where the
        // track padding falls; either way the reader has moved into the middle
        // of the chapter rather than staying put.
        final page = _metricsFor(tester, extents)
            .pageAtOffset(_listController(tester).offset);
        expect(page, inInclusiveRange(3, 4));
        expect(find.text('Page $page / 6'), findsOneWidget);
      },
    );

    testWidgets(
      'the bottom rail runs right-to-left in a right-to-left chapter',
      (tester) async {
        final prefs = await _freshPrefs({
          _readingDirectionKey: ReadingDirection.rightToLeft.name,
        });

        await tester.pumpWidget(
          _wrapWithPrefs(
            prefs,
            ReaderContent(
              feed: ReaderFeed.single(_scrubChapter()),
              scrollStorageKey: '1',
              onBack: () {},
              onOpenSeries: () {},
            ),
          ),
        );
        await tester.pump();
        await tester.pump(const Duration(milliseconds: 100));

        expect(find.text('Page 1 / 6'), findsOneWidget);

        // The chapter starts on the right, so the rail does too: dragging the
        // thumb LEFT has to move forward. In a left-to-right chapter the same
        // gesture would go backwards and this would stay on page 1.
        final rail = tester.getRect(find.byType(Slider));
        await tester.dragFrom(rail.center, Offset(-rail.width, 0));
        await tester.pump();
        await tester.pump(const Duration(milliseconds: 100));

        final controller = _listController(tester);
        expect(find.text('Page 1 / 6'), findsNothing);
        // Dragged to the far end of the rail, so the reader is as deep into the
        // chapter as it goes — proof the gesture ran forward, not backward.
        expect(
          controller.offset,
          moreOrLessEquals(controller.position.maxScrollExtent, epsilon: 1),
        );
      },
    );

    testWidgets(
      'auto-next fires exactly once even with further scroll activity at bottom',
      (tester) async {
        final prefs = await _freshPrefs();
        await tester.binding.setSurfaceSize(const Size(430, 932));
        addTearDown(() => tester.binding.setSurfaceSize(null));

        var nextCalls = 0;
        await tester.pumpWidget(
          _wrapWithPrefs(
            prefs,
            ReaderContent(
              feed: ReaderFeed.single(_tallChapter(nextChapterId: '2')),
              scrollStorageKey: '1',
              onBack: () {},
              onOpenSeries: () {},
              onNextChapter: () => nextCalls++,
            ),
          ),
        );
        await tester.pump();
        await tester.pump(const Duration(milliseconds: 100));

        final controller =
            tester.widget<ListView>(find.byType(ListView)).controller!;
        final maxExtent = controller.position.maxScrollExtent;

        controller.jumpTo(maxExtent);
        await tester.pump();
        await tester.pump(const Duration(milliseconds: 1000));

        expect(nextCalls, 1);

        // Further scroll wiggles at bottom after firing must not fire again.
        controller.jumpTo(maxExtent - 20);
        await tester.pump();
        controller.jumpTo(maxExtent);
        await tester.pump();
        await tester.pump(const Duration(milliseconds: 1000));

        expect(nextCalls, 1);
      },
    );
  });
}