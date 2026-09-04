import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/features/reader/models/reader_page.dart';
import 'package:manhwamaniacs/features/reader/utils/page_extents.dart';
import 'package:manhwamaniacs/features/reader/utils/page_layout.dart';
import 'package:manhwamaniacs/features/settings/models/reader_defaults.dart';

ReaderPage _page(int number, {int? width, int? height}) => ReaderPage(
      id: '$number',
      number: number,
      imageUrl: '/pages/$number.jpg',
      width: width,
      height: height,
    );

ReaderPageMetrics _verticalMetrics(
  List<double> ratios, {
  double viewportWidth = 400,
  double viewportHeight = 900,
  double zoom = 1,
  ReaderFitMode fitMode = ReaderFitMode.width,
}) =>
    ReaderPageMetrics(
      ratios: ratios,
      direction: ReadingDirection.vertical,
      fitMode: fitMode,
      viewportWidth: viewportWidth,
      viewportHeight: viewportHeight,
      zoom: zoom,
    );

void main() {
  group('ReaderPageExtents', () {
    test('seeds ratios from the payload and marks those pages resolved', () {
      final extents = ReaderPageExtents([
        _page(1, width: 800, height: 1200),
        _page(2),
      ]);

      expect(extents.isResolved(0), isTrue);
      expect(extents.ratioAt(0), closeTo(800 / 1200, 1e-9));
      expect(extents.isResolved(1), isFalse);
      expect(extents.ratioAt(1), defaultAspectRatio);
    });

    test('staged sizes stay out of the layout until committed', () {
      final extents = ReaderPageExtents([_page(1)]);

      expect(
        extents.submitMeasuredSize(0, pixelWidth: 900, pixelHeight: 16000),
        isTrue,
      );
      // Still the fallback: whoever owns the scroll position has to read the
      // old geometry before this lands.
      expect(extents.ratioAt(0), defaultAspectRatio);
      expect(extents.pendingRatios[0], closeTo(900 / 16000, 1e-9));

      extents.commitPending();

      expect(extents.ratioAt(0), closeTo(900 / 16000, 1e-9));
      expect(extents.pendingRatios, isEmpty);
    });

    test('a page never changes extent twice — first write wins', () {
      final extents = ReaderPageExtents([_page(1)]);

      extents.submitMeasuredSize(0, pixelWidth: 900, pixelHeight: 16000);
      extents.commitPending();
      expect(
        extents.submitMeasuredSize(0, pixelWidth: 100, pixelHeight: 100),
        isFalse,
      );

      expect(extents.ratioAt(0), closeTo(900 / 16000, 1e-9));
    });

    test('a page whose size came from the payload is never re-measured', () {
      final extents = ReaderPageExtents([_page(1, width: 800, height: 1200)]);

      expect(
        extents.submitMeasuredSize(0, pixelWidth: 900, pixelHeight: 16000),
        isFalse,
      );
      expect(extents.ratioAt(0), closeTo(800 / 1200, 1e-9));
    });

    test('rejects unusable sizes rather than laying out a zero-height page', () {
      final extents = ReaderPageExtents([_page(1)]);

      expect(
        extents.submitMeasuredSize(0, pixelWidth: 0, pixelHeight: 0),
        isFalse,
      );
      expect(
        extents.submitMeasuredSize(-1, pixelWidth: 10, pixelHeight: 10),
        isFalse,
      );
      expect(extents.ratioAt(0), defaultAspectRatio);
    });

    test('notifies once per newly staged size', () {
      final extents = ReaderPageExtents([_page(1), _page(2)]);
      var notifications = 0;
      extents.addListener(() => notifications++);

      extents.submitMeasuredSize(0, pixelWidth: 800, pixelHeight: 1200);
      extents.submitMeasuredSize(0, pixelWidth: 800, pixelHeight: 1200);
      extents.submitMeasuredSize(1, pixelWidth: 800, pixelHeight: 2400);

      expect(notifications, 2);
    });
  });

  group('ReaderPageMetrics', () {
    test('vertical extent follows the ratio at the content width', () {
      final metrics = _verticalMetrics([800 / 1200]);

      expect(metrics.contentWidth, 400);
      expect(metrics.extentAt(0), closeTo(400 * 1200 / 800, 1e-9));
    });

    test('vertical extent scales with zoom', () {
      final ratios = [800 / 1200];
      expect(
        _verticalMetrics(ratios, zoom: 2).extentAt(0),
        greaterThan(_verticalMetrics(ratios).extentAt(0)),
      );
    });

    test('content width is capped at maxContentWidth up to 1x zoom', () {
      // A tablet-width viewport must not stretch a phone-shaped page.
      expect(
        _verticalMetrics([2 / 3], viewportWidth: 1200).contentWidth,
        maxContentWidth,
      );
      // Past 1x the cap is lifted: zooming in is meant to overflow.
      expect(
        _verticalMetrics([2 / 3], viewportWidth: 1200, zoom: 2).contentWidth,
        2400,
      );
    });

    test('fit height gives every page exactly one screenful', () {
      final metrics = _verticalMetrics(
        [900 / 16000, 800 / 1200],
        fitMode: ReaderFitMode.height,
      );

      expect(metrics.extentAt(0), 900);
      expect(metrics.extentAt(1), 900);
    });

    test('offsetToPage starts at the list padding and sums earlier pages', () {
      final metrics = _verticalMetrics([2 / 3, 2 / 3, 2 / 3]);
      final pageHeight = metrics.extentAt(0);

      expect(metrics.offsetToPage(1), readerListLeadingPadding);
      expect(
        metrics.offsetToPage(3),
        closeTo(readerListLeadingPadding + pageHeight * 2, 1e-9),
      );
    });

    test('offsetToPage clamps out-of-range page numbers', () {
      final metrics = _verticalMetrics([2 / 3, 2 / 3]);

      expect(metrics.offsetToPage(0), metrics.offsetToPage(1));
      expect(metrics.offsetToPage(99), metrics.offsetToPage(2));
    });

    test('pageAtOffset is the inverse of offsetToPage', () {
      final metrics = _verticalMetrics([2 / 3, 900 / 16000, 2 / 3, 1]);

      for (var page = 1; page <= metrics.pageCount; page++) {
        expect(
          metrics.pageAtOffset(metrics.offsetToPage(page)),
          page,
          reason: 'jumping to page $page must report page $page',
        );
      }
    });

    test('pageAtOffset accounts for pages of wildly different heights', () {
      // Page 2 is a tall webtoon strip; page 3 starts far below it.
      final metrics = _verticalMetrics([2 / 3, 900 / 16000, 2 / 3]);
      final strip = metrics.extentAt(1);

      expect(metrics.pageAtOffset(0), 1);
      expect(metrics.pageAtOffset(readerListLeadingPadding + strip / 2), 2);
    });

    test('an offset above the first page still reads as page 1', () {
      final metrics = _verticalMetrics([2 / 3, 2 / 3]);

      expect(metrics.pageAtOffset(-5000), 1);
    });

    test('page lookup stays exact across a long Read-all feed', () {
      // Geometry is answered from a prefix sum rather than a walk, so this
      // pins the two together: every page start, every reverse lookup and the
      // total must agree with summing the extents by hand — across the
      // hundreds of alternating strip/print pages Read-all produces, which is
      // where a binary search would drift if it were subtly wrong.
      final ratios = [
        for (var index = 0; index < 300; index++)
          index.isEven ? 2 / 3 : 900 / 16000,
      ];
      final metrics = _verticalMetrics(ratios);

      var walked = readerListLeadingPadding;
      for (var index = 0; index < ratios.length; index++) {
        expect(metrics.offsetToPage(index + 1), closeTo(walked, 1e-6));
        expect(metrics.pageAtOffset(walked), index + 1);
        walked += metrics.extentAt(index);
      }
      expect(
        metrics.totalPagesExtent,
        closeTo(walked - readerListLeadingPadding, 1e-6),
      );
    });

    test('totalPagesExtent sums every page and excludes list padding', () {
      final metrics = _verticalMetrics([2 / 3, 2 / 3]);

      expect(
        metrics.totalPagesExtent,
        closeTo(metrics.extentAt(0) + metrics.extentAt(1), 1e-9),
      );
    });

    test('horizontal extent is one viewport tall plus the page gap', () {
      final metrics = ReaderPageMetrics(
        ratios: const [0.5],
        direction: ReadingDirection.leftToRight,
        fitMode: ReaderFitMode.width,
        viewportWidth: 400,
        viewportHeight: 900,
      );

      expect(metrics.extentAt(0), closeTo(900 * 0.5 + readerPagedGap, 1e-9));
    });

    test('a nonsense ratio falls back instead of producing a zero extent', () {
      final metrics = _verticalMetrics([0, double.nan]);

      final fallback = _verticalMetrics([defaultAspectRatio]).extentAt(0);
      expect(metrics.extentAt(0), fallback);
      expect(metrics.extentAt(1), fallback);
    });
  });

  group('scrollCorrectionForExtentChange', () {
    test('a page entirely above the viewport shifts everything below it', () {
      // Page starts at 0, was 600 tall, resolves to 3000. The viewport top is
      // at 1000 — well past it — so the visible page just moved down 2400.
      expect(
        scrollCorrectionForExtentChange(
          pageStart: 0,
          oldExtent: 600,
          newExtent: 3000,
          scrollOffset: 1000,
        ),
        2400,
      );
    });

    test('a page shrinking above the viewport pulls the offset back', () {
      expect(
        scrollCorrectionForExtentChange(
          pageStart: 0,
          oldExtent: 3000,
          newExtent: 600,
          scrollOffset: 4000,
        ),
        -2400,
      );
    });

    test('a page at or below the viewport top needs no correction', () {
      expect(
        scrollCorrectionForExtentChange(
          pageStart: 1000,
          oldExtent: 600,
          newExtent: 3000,
          scrollOffset: 1000,
        ),
        0,
      );
      expect(
        scrollCorrectionForExtentChange(
          pageStart: 5000,
          oldExtent: 600,
          newExtent: 3000,
          scrollOffset: 1000,
        ),
        0,
      );
    });

    test('a page straddling the viewport top is corrected in proportion', () {
      // Half of the old page is above the edge, so half the growth pushed the
      // visible content down.
      expect(
        scrollCorrectionForExtentChange(
          pageStart: 0,
          oldExtent: 1000,
          newExtent: 3000,
          scrollOffset: 500,
        ),
        1000,
      );
    });

    test('an unchanged extent never moves the reader', () {
      expect(
        scrollCorrectionForExtentChange(
          pageStart: 0,
          oldExtent: 600,
          newExtent: 600,
          scrollOffset: 1000,
        ),
        0,
      );
    });
  });
}
