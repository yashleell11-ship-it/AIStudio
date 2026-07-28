import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/shared/widgets/series_detail/series_detail_meta.dart';

void main() {
  group('seriesDetailMetaLine', () {
    test('joins every known fact in a fixed order', () {
      expect(
        seriesDetailMetaLine(
          latestChapterLabel: 'Chapter 322',
          chapterCount: 322,
          pageCount: 8940,
          readPct: 61.4,
        ),
        'Latest: Chapter 322  ·  322 chapters  ·  8,940 pages  ·  61% read',
      );
    });

    test('renders the source page shape when only catalog facts are known', () {
      // The source catalog knows nothing about pages read; the same builder has
      // to produce its line too, or the two pages drift apart again.
      expect(
        seriesDetailMetaLine(
          latestChapterLabel: 'Chapter 120',
          chapterCount: 120,
        ),
        'Latest: Chapter 120  ·  120 chapters',
      );
    });

    test('never states a count of zero', () {
      // Zero is how "not known" arrives from both payloads, so it has to drop
      // out rather than print "0 chapters" / "0 pages".
      const unknown = 0;
      expect(
        seriesDetailMetaLine(
          latestChapterLabel: 'Chapter 7',
          chapterCount: unknown,
        ),
        'Latest: Chapter 7',
      );
      // Passing the "unknown" value explicitly is the whole assertion here.
      // ignore: avoid_redundant_argument_values
      expect(seriesDetailMetaLine(chapterCount: 3, pageCount: unknown), '3 chapters');
    });

    test('singularises a one-chapter, one-page series', () {
      expect(
        seriesDetailMetaLine(chapterCount: 1, pageCount: 1),
        '1 chapter  ·  1 page',
      );
    });

    test('keeps 0% read, which is an answer rather than a missing one', () {
      expect(
        seriesDetailMetaLine(chapterCount: 2, readPct: 0),
        '2 chapters  ·  0% read',
      );
    });

    test('rounds the read percentage to whole numbers', () {
      expect(
        seriesDetailMetaLine(chapterCount: 2, readPct: 99.6),
        '2 chapters  ·  100% read',
      );
    });

    test('drops a blank latest-chapter label', () {
      expect(
        seriesDetailMetaLine(latestChapterLabel: '   ', chapterCount: 4),
        '4 chapters',
      );
    });

    test('returns null when nothing at all is known', () {
      expect(seriesDetailMetaLine(chapterCount: 0), isNull);
    });
  });

  group('seriesChapterProgressText', () {
    test('unread chapters state the page count alone', () {
      expect(seriesChapterProgressText(pageCount: 20), '20 pages');
    });

    test('part-read chapters state position out of total', () {
      expect(
        seriesChapterProgressText(pageCount: 20, page: 7),
        '7/20 pages',
      );
    });

    test('finished chapters read as complete whatever page was last seen', () {
      // Readers routinely stop one page short of the end marker; a finished
      // chapter still has to read 20/20, not 19/20.
      expect(
        seriesChapterProgressText(pageCount: 20, page: 19, completed: true),
        '20/20 pages',
      );
    });

    test('returns null when the page count is unknown', () {
      expect(seriesChapterProgressText(pageCount: 0, page: 3), isNull);
      expect(seriesChapterProgressText(pageCount: -1), isNull);
    });
  });
}
