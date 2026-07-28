import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/features/reader/utils/reader_scrub.dart';

void main() {
  group('reader_scrub', () {
    test('the rail spans page 1 to the last page', () {
      // Both ends have to be reachable: a rail whose maximum was anything other
      // than the page count could never be dragged onto the final page.
      expect(readerScrubValue(1, 20), 1);
      expect(readerScrubValue(20, 20), 20);
      expect(readerScrubMax(20), 20);
      expect(readerScrubPage(1, 20), 1);
      expect(readerScrubPage(20, 20), 20);
    });

    test('one stop per page so a drag lands on whole pages', () {
      expect(readerScrubDivisions(20), 19);
      expect(readerScrubDivisions(2), 1);
    });

    test('a value between two stops rounds to the nearer page', () {
      expect(readerScrubPage(4.4, 20), 4);
      expect(readerScrubPage(4.6, 20), 5);
    });

    test('values outside the chapter clamp into it', () {
      expect(readerScrubPage(0, 20), 1);
      expect(readerScrubPage(-5, 20), 1);
      expect(readerScrubPage(999, 20), 20);
      expect(readerScrubPage(double.nan, 20), 1);
      // The reported page is measured back from the scroll offset and can lag
      // a jump by a frame; an out-of-range slider value would assert.
      expect(readerScrubValue(99, 20), 20);
      expect(readerScrubValue(0, 20), 1);
    });

    test('a one-page chapter still produces a valid, disabled range', () {
      expect(readerScrubEnabled(1), isFalse);
      expect(readerScrubEnabled(0), isFalse);
      expect(readerScrubEnabled(2), isTrue);
      // min is 1, so max must stay above it or the slider divides by zero
      // working out where to draw the thumb.
      expect(readerScrubMax(1), greaterThan(1));
      expect(readerScrubMax(0), greaterThan(1));
      expect(readerScrubDivisions(1), isNull);
    });

    test('an empty chapter never reports page 0', () {
      expect(readerScrubValue(1, 0), 1);
      expect(readerScrubPage(3, 0), 1);
    });
  });
}
