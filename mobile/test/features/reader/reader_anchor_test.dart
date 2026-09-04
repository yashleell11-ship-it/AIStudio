import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/features/reader/utils/page_extents.dart';
import 'package:manhwamaniacs/features/reader/utils/reader_anchor.dart';
import 'package:manhwamaniacs/features/settings/models/reader_defaults.dart';

/// Webtoon geometry: a vertical, fit-width feed whose pages are tall strips.
/// A 400pt content width at a 0.5 ratio makes every page exactly 800pt of
/// scroll extent, so an offset can be reasoned about by hand.
ReaderPageMetrics _metrics({
  int pages = 5,
  Map<int, double> leadingInsets = const {},
}) =>
    ReaderPageMetrics(
      ratios: List.filled(pages, 0.5),
      direction: ReadingDirection.vertical,
      fitMode: ReaderFitMode.width,
      viewportWidth: 400,
      viewportHeight: 900,
      leadingInsets: leadingInsets,
    );

void main() {
  group('anchorAtOffset', () {
    test('the top of the chapter is page 1, at the probe point', () {
      final metrics = _metrics();
      final anchor = anchorAtOffset(metrics, 0);

      expect(anchor.page, 1);
      // The reading probe sits [readerVisiblePageLead] below the viewport top,
      // so "the very top" is a small way into page 1, not exactly 0.
      final extent = metrics.extentAt(0);
      expect(
        anchor.fraction,
        closeTo((readerVisiblePageLead - readerListLeadingPadding) / extent, 1e-9),
      );
    });

    test('halfway down page 3 reports page 3 at ~0.5', () {
      final metrics = _metrics();
      final extent = metrics.extentAt(0);
      // Put the probe exactly at the middle of page 3.
      final offset =
          metrics.offsetToPage(3) + extent / 2 - readerVisiblePageLead;

      final anchor = anchorAtOffset(metrics, offset);

      expect(anchor.page, 3);
      expect(anchor.fraction, closeTo(0.5, 1e-9));
    });

    test('scrolling past the end saturates at the last page rather than '
        'reporting a page that is not there', () {
      final metrics = _metrics();
      final anchor = anchorAtOffset(metrics, 99999);
      expect(anchor.page, 5);
      expect(anchor.fraction, 1.0);
    });

    test('the fraction never escapes 0..1', () {
      final metrics = _metrics();
      for (final offset in [-5000.0, 0.0, 1.0, 999999.0]) {
        final anchor = anchorAtOffset(metrics, offset);
        expect(anchor.fraction, inInclusiveRange(0, 1));
        expect(anchor.page, greaterThanOrEqualTo(1));
      }
    });

    test('an empty chapter answers page 1 rather than throwing', () {
      final anchor = anchorAtOffset(_metrics(pages: 0), 1234);
      expect(anchor.page, 1);
      expect(anchor.fraction, 0);
    });

    test('a seam divider above a page is not part of that page', () {
      // A continued chapter reserves [kChapterSeamExtent] above its first
      // page. That space is not the page, so a probe just past the divider is
      // near the START of the page, not partway into it.
      final metrics = _metrics(leadingInsets: const {2: 96});
      final inset = metrics.leadingInsetAt(2);
      final offset =
          metrics.offsetToPage(3) + inset - readerVisiblePageLead + 1;

      final anchor = anchorAtOffset(metrics, offset);

      expect(anchor.page, 3);
      expect(anchor.fraction, lessThan(0.01));
    });
  });

  group('offsetForAnchor is the exact inverse', () {
    test('capture then restore lands on the same offset', () {
      final metrics = _metrics();
      // Five 800px pages, so the chapter runs to ~3500 of usable offset.
      for (final offset in [0.0, 120.0, 1500.0, 2777.25, 3500.0]) {
        final anchor = anchorAtOffset(metrics, offset);
        final restored = offsetForAnchor(metrics, anchor);
        expect(restored, closeTo(offset, 1e-6), reason: 'offset $offset');
      }
    });

    test('round-trips across a seam too', () {
      final metrics = _metrics(leadingInsets: const {2: 96});
      final offset = metrics.offsetToPage(3) + 400;
      final anchor = anchorAtOffset(metrics, offset);
      expect(offsetForAnchor(metrics, anchor), closeTo(offset, 1e-6));
    });

    test('a page past the end degrades to the last page, never off the end',
        () {
      final metrics = _metrics(pages: 3);
      final restored = offsetForAnchor(metrics, (page: 99, fraction: 0.5));

      final lastPageMiddle = metrics.offsetToPage(3) +
          metrics.extentAt(2) / 2 -
          readerVisiblePageLead;
      expect(restored, closeTo(lastPageMiddle, 1e-6));
    });

    test('never returns a negative offset', () {
      final metrics = _metrics();
      expect(offsetForAnchor(metrics, (page: 1, fraction: 0)), 0);
    });

    test('an empty chapter answers 0', () {
      expect(offsetForAnchor(_metrics(pages: 0), (page: 4, fraction: 0.5)), 0);
    });
  });

  group('anchorPageIsMissing', () {
    test('says so only when the chapter genuinely lost that page', () {
      expect(anchorPageIsMissing(7, 11), isFalse);
      expect(anchorPageIsMissing(11, 11), isFalse);
      expect(anchorPageIsMissing(12, 11), isTrue);
      // A chapter whose page count is unknown makes no claim either way —
      // "not known to be stale" is not the same as "verified fresh".
      expect(anchorPageIsMissing(12, 0), isFalse);
    });
  });
}
