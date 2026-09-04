import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/features/reader/models/reader_chapter.dart';
import 'package:manhwamaniacs/features/reader/models/reader_feed.dart';
import 'package:manhwamaniacs/features/reader/models/reader_page.dart';
import 'package:manhwamaniacs/features/reader/utils/page_extents.dart';
import 'package:manhwamaniacs/features/settings/models/reader_defaults.dart';

ReaderChapter _chapter(String id, int pages) => ReaderChapter(
      id: id,
      seriesId: 'series',
      title: 'Chapter $id',
      pageCount: pages,
      pages: [
        for (var n = 1; n <= pages; n++)
          ReaderPage(id: '$id:$n', number: n, imageUrl: 'http://x/$id/$n'),
      ],
    );

void main() {
  group('ReaderFeed', () {
    test('one chapter is exactly today\'s reader', () {
      final feed = ReaderFeed.single(_chapter('a', 3));
      expect(feed.isSingleChapter, isTrue);
      expect(feed.length, 3);
      expect(feed.pageWithinChapterAt(0), 1);
      expect(feed.pageWithinChapterAt(2), 3);
      // Nothing was crossed to reach the first chapter, so no seam.
      expect(feed.startsLaterChapter(0), isFalse);
    });

    test('pages concatenate in reading order', () {
      final feed = ReaderFeed.of([
        _chapter('a', 2),
        _chapter('b', 3),
        _chapter('c', 1),
      ]);
      expect(feed.length, 6);
      expect(
        [for (final page in feed.pages) page.id],
        ['a:1', 'a:2', 'b:1', 'b:2', 'b:3', 'c:1'],
      );
    });

    test('a page knows which chapter it belongs to and its number in it', () {
      final feed = ReaderFeed.of([_chapter('a', 2), _chapter('b', 3)]);

      expect(feed.chapterAt(0).id, 'a');
      expect(feed.chapterAt(1).id, 'a');
      expect(feed.chapterAt(2).id, 'b');
      expect(feed.chapterAt(4).id, 'b');

      // The number PROGRESS is recorded against — chapter-local, not flat.
      // Reading into the second chapter must record its page 1, not page 3.
      expect(feed.pageWithinChapterAt(2), 1);
      expect(feed.pageWithinChapterAt(4), 3);
    });

    test('a seam sits at every chapter start except the first', () {
      final feed = ReaderFeed.of([
        _chapter('a', 2),
        _chapter('b', 2),
        _chapter('c', 2),
      ]);
      expect(feed.startsLaterChapter(0), isFalse);
      expect(feed.startsLaterChapter(1), isFalse);
      expect(feed.startsLaterChapter(2), isTrue);
      expect(feed.startsLaterChapter(4), isTrue);
    });

    test('a chapter can be located by id and page', () {
      final feed = ReaderFeed.of([_chapter('a', 2), _chapter('b', 3)]);
      expect(feed.flatIndexOf(chapterId: 'b', page: 2), 3);
      expect(feed.flatIndexOf(chapterId: 'a', page: 1), 0);
      expect(feed.flatIndexOf(chapterId: 'nope', page: 1), isNull);
      // Out-of-range pages clamp into the chapter rather than escaping it.
      expect(feed.flatIndexOf(chapterId: 'a', page: 99), 1);
    });

    test('appending extends forward and leaves every existing index alone', () {
      final before = ReaderFeed.single(_chapter('a', 2));
      final after = before.withAppended(_chapter('b', 3));

      expect(after.length, 5);
      expect(after.chapterAt(0).id, 'a');
      expect(after.pageWithinChapterAt(1), 2);
      expect(after.chapterAt(2).id, 'b');
      // The original is untouched — the widget compares the two to work out
      // what moved.
      expect(before.length, 2);
    });

    test('prepending shifts every index by the new chapter\'s page count', () {
      final before = ReaderFeed.single(_chapter('b', 2));
      final after = before.withPrepended(_chapter('a', 3));

      expect(after.length, 5);
      expect(after.chapterAt(0).id, 'a');
      // What was flat index 0 is now flat index 3 — the shift the caller must
      // pay for with a scroll correction.
      expect(after.chapterAt(3).id, 'b');
      expect(after.pageWithinChapterAt(3), 1);
      expect(after.startOfChapter(1), 3);
    });

    test('a chapter already in the feed is never added twice', () {
      final feed = ReaderFeed.of([_chapter('a', 2), _chapter('b', 2)]);
      // A boundary trigger that fires twice must not double the chapter.
      expect(identical(feed.withAppended(_chapter('b', 2)), feed), isTrue);
      expect(identical(feed.withPrepended(_chapter('a', 2)), feed), isTrue);
      expect(ReaderFeed.of([_chapter('a', 2), _chapter('a', 2)]).length, 2);
    });

    test('trimming releases chapters but never the last one', () {
      final feed = ReaderFeed.of([
        _chapter('a', 2),
        _chapter('b', 2),
        _chapter('c', 2),
      ]);
      expect(feed.withoutLeadingChapters(1).chapters.map((c) => c.id), ['b', 'c']);
      expect(feed.withoutTrailingChapters(1).chapters.map((c) => c.id), ['a', 'b']);
      // A feed with no pages has nothing to render and nowhere to put the
      // reader, so the last chapter is not droppable.
      expect(feed.withoutLeadingChapters(99).chapters, hasLength(1));
      expect(feed.withoutTrailingChapters(99).chapters, hasLength(1));
    });
  });

  group('ReaderPageExtents growth', () {
    List<ReaderPage> pages(int count) => [
          for (var n = 1; n <= count; n++)
            ReaderPage(id: '$n', number: n, imageUrl: '', width: 800, height: 1200),
        ];

    test('appending keeps every resolved ratio at the same index', () {
      final extents = ReaderPageExtents.fromRatios([0.5, null]);
      extents.appendPages(pages(2));

      expect(extents.length, 4);
      expect(extents.ratioAt(0), 0.5);
      expect(extents.isResolved(1), isFalse);
      expect(extents.ratioAt(2), closeTo(800 / 1200, 1e-9));
    });

    test('prepending moves every resolved ratio along with its page', () {
      final extents = ReaderPageExtents.fromRatios([0.5, 0.25]);
      extents.prependPages(pages(2));

      expect(extents.length, 4);
      expect(extents.ratioAt(2), 0.5);
      expect(extents.ratioAt(3), 0.25);
    });

    test('a measurement staged across a prepend follows its page', () {
      final extents = ReaderPageExtents.fromRatios([null, null]);
      expect(
        extents.submitMeasuredSize(1, pixelWidth: 100, pixelHeight: 200),
        isTrue,
      );

      extents.prependPages(pages(3));
      // Dropping it would leave that page permanently at the default ratio.
      expect(extents.pendingRatios.keys, [4]);
      extents.commitPending();
      expect(extents.ratioAt(4), closeTo(0.5, 1e-9));
    });

    test('trimming drops the right end and forgets its staged sizes', () {
      final extents = ReaderPageExtents.fromRatios([0.5, 0.25, null, null]);
      expect(
        extents.submitMeasuredSize(3, pixelWidth: 100, pixelHeight: 100),
        isTrue,
      );

      extents.removeTrailingPages(2);
      expect(extents.length, 2);
      expect(extents.pendingRatios, isEmpty);

      extents.removeLeadingPages(1);
      expect(extents.length, 1);
      expect(extents.ratioAt(0), 0.25);
    });
  });

  group('ReaderPageMetrics seam insets', () {
    test('a seam adds to the extent of the page it sits above', () {
      const withoutSeam = ReaderPageMetrics(
        ratios: [1, 1, 1],
        direction: ReadingDirection.vertical,
        fitMode: ReaderFitMode.width,
        viewportWidth: 400,
        viewportHeight: 800,
      );
      const withSeam = ReaderPageMetrics(
        ratios: [1, 1, 1],
        direction: ReadingDirection.vertical,
        fitMode: ReaderFitMode.width,
        viewportWidth: 400,
        viewportHeight: 800,
        leadingInsets: {1: 60},
      );

      expect(withSeam.extentAt(0), withoutSeam.extentAt(0));
      expect(withSeam.extentAt(1), withoutSeam.extentAt(1) + 60);
      // Everything after the seam moves by exactly the divider's height —
      // which is the whole reason the geometry has to know about it rather
      // than the list quietly drawing one.
      expect(withSeam.offsetToPage(3), withoutSeam.offsetToPage(3) + 60);
      expect(withSeam.totalPagesExtent, withoutSeam.totalPagesExtent + 60);
    });

    test('the page counter respects the seam it just scrolled past', () {
      const metrics = ReaderPageMetrics(
        ratios: [1, 1],
        direction: ReadingDirection.vertical,
        fitMode: ReaderFitMode.width,
        viewportWidth: 400,
        viewportHeight: 800,
        leadingInsets: {1: 200},
      );
      // Page 2 starts 200px later than it would without the divider, so an
      // offset inside the divider is still page 1.
      final page2Start = metrics.offsetToPage(2);
      expect(metrics.pageAtOffset(page2Start - 201 - readerVisiblePageLead), 1);
      expect(metrics.pageAtOffset(page2Start - readerVisiblePageLead), 2);
    });
  });
}
