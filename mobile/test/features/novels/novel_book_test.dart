import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/features/novels/utils/novel_book.dart';

void main() {
  group('front matter', () {
    test('byline is present only when the source named an author', () {
      expect(byline('Neil Gaiman'), 'by Neil Gaiman');
      expect(byline('  Neil Gaiman  '), 'by Neil Gaiman');
      expect(byline(''), isNull);
      expect(byline('   '), isNull);
      expect(byline(null), isNull);
    });

    test('chapter counts are separated and pluralised', () {
      expect(formatChapterCount(1), '1 chapter');
      expect(formatChapterCount(412), '412 chapters');
      expect(formatChapterCount(1240), '1,240 chapters');
      expect(formatChapterCount(0), isNull);
      expect(formatChapterCount(null), isNull);
    });

    test('status is capitalised because sources are inconsistent', () {
      expect(formatStatus('ongoing'), 'Ongoing');
      expect(formatStatus('Completed'), 'Completed');
      expect(formatStatus('  hiatus'), 'Hiatus');
      expect(formatStatus(''), isNull);
      expect(formatStatus(null), isNull);
    });

    test('a blurb collapses the markup whitespace a clamp would render as gaps',
        () {
      expect(shelfBlurb('  A boy\n\n  and   his\tdog. '), 'A boy and his dog.');
      expect(shelfBlurb('   '), isNull);
      expect(shelfBlurb(null), isNull);
    });

    test('genres are de-duplicated case-insensitively and capped at six', () {
      expect(
        shelfGenres(['Action', 'action', ' ACTION ', 'Drama']),
        ['Action', 'Drama'],
      );
      expect(
        shelfGenres(List.generate(20, (i) => 'Genre $i')),
        hasLength(kMaxShelfGenres),
      );
      expect(shelfGenres(null), isEmpty);
      expect(shelfGenres(['', '  ']), isEmpty);
    });
  });

  group('whole-book estimate', () {
    test('refuses to project from a single measured chapter', () {
      final estimate = estimateSeriesLength(400, [2500]);
      expect(estimate.sampleSize, 1);
      expect(estimate.meanWords, isNull);
      expect(estimate.totalWords, isNull);
      expect(formatEstimatedWords(estimate), isNull);
      expect(formatEstimatedTotal(estimate), isNull);
    });

    test('refuses to project when the source reports no chapter count', () {
      final estimate = estimateSeriesLength(null, [2500, 2600, 2400]);
      expect(estimate.chapters, 0);
      expect(estimate.totalWords, isNull);
    });

    test('projects the mean of the sample across the catalogue', () {
      final estimate = estimateSeriesLength(400, [2000, 3000]);
      expect(estimate.sampleSize, 2);
      expect(estimate.meanWords, 2500);
      expect(estimate.totalWords, 1000000);
      expect(estimate.minutes, 4000);
      expect(formatEstimatedWords(estimate), '≈ 1.0M words');
      expect(formatEstimatedTotal(estimate), '≈ 67 h');
    });

    test('zero and negative samples are not counted as measured chapters', () {
      final estimate = estimateSeriesLength(10, [0, -5, 1000, 2000]);
      expect(estimate.sampleSize, 2);
      expect(estimate.meanWords, 1500);
    });

    test('a short book reports minutes rather than a rounded-to-zero hour', () {
      final estimate = estimateSeriesLength(2, [1000, 1000]);
      expect(estimate.minutes, 8);
      expect(formatEstimatedTotal(estimate), '≈ 8 min');
    });
  });

  group('table of contents', () {
    test('the number goes in its own column and is not repeated in the title',
        () {
      final entry = tocEntry(number: 12, title: 'Chapter 12: The Gate Opens');
      expect(entry.ordinal, '12');
      expect(entry.title, 'The Gate Opens');
    });

    test('a chapter with nothing but a number has no title column', () {
      final entry = tocEntry(number: 12, title: 'Chapter 12');
      expect(entry.ordinal, '12');
      expect(entry.title, isNull);
    });

    test('an unnumbered chapter leads with its title', () {
      final entry = tocEntry(number: null, title: 'Epilogue');
      expect(entry.ordinal, isNull);
      expect(entry.title, 'Epilogue');
    });

    test('a decimal chapter keeps its decimal', () {
      expect(tocEntry(number: 12.5, title: null).ordinal, '12.5');
      expect(formatChapterNumber(12), '12');
      expect(formatChapterNumber(12.5), '12.5');
      expect(formatChapterNumber(double.nan), '');
    });
  });

  group('drop cap', () {
    const opener =
        'The gate had stood shut for four hundred years, and nobody living '
        'could remember who had closed it or why they had bothered.';

    test('caps a prose opener', () {
      final cap = splitDropCap(opener);
      expect(cap, isNotNull);
      expect(cap!.initial, 'T');
      expect(cap.rest, startsWith('he gate had stood'));
      expect('${cap.initial}${cap.rest}', opener);
    });

    test('declines a dialogue opener — a raised quote reads as an error', () {
      expect(
        splitDropCap(
          '"Wait," she said, and the whole corridor went quiet around her, '
          'which was somehow worse than any answer she could have given.',
        ),
        isNull,
      );
      expect(
        splitDropCap(
          '“Wait,” she said, and the whole corridor went quiet '
          'around her, which was somehow worse than an answer.',
        ),
        isNull,
      );
    });

    test('declines an epigraph or dateline too short to carry an initial', () {
      expect(splitDropCap('Three days earlier.'), isNull);
      expect(splitDropCap(''), isNull);
      expect(splitDropCap(null), isNull);
    });

    test('a numeral opener is not a letter', () {
      expect(
        splitDropCap(
          '1987 was the year the river froze all the way to the bend, and the '
          'year everyone afterwards agreed things had started to go wrong.',
        ),
        isNull,
      );
    });
  });

  group('scene breaks', () {
    test('recognises the ornaments translators actually use', () {
      expect(isSceneBreak('***'), isTrue);
      expect(isSceneBreak('* * *'), isTrue);
      expect(isSceneBreak('- - -'), isTrue);
      expect(isSceneBreak('◇◇◇'), isTrue);
      expect(isSceneBreak('  ---  '), isTrue);
    });

    test('prose is never an ornament, however it opens', () {
      expect(isSceneBreak('— and then nothing'), isFalse);
      expect(isSceneBreak('Chapter 3'), isFalse);
      expect(isSceneBreak(''), isFalse);
      // Long enough to be a line of dashes in the text, not a marker.
      expect(isSceneBreak('-' * 40), isFalse);
    });
  });

  group('reading time', () {
    test('minutes round at 250 wpm and never fall below one for real text', () {
      expect(readingMinutes(0), 0);
      expect(readingMinutes(-10), 0);
      expect(readingMinutes(10), 1);
      expect(readingMinutes(2500), 10);
    });

    test('switches to hours past ninety minutes', () {
      expect(formatReadingTime(2000), '~8 min');
      // Exactly ninety minutes is still the last minute-shaped answer.
      expect(formatReadingTime(22500), '~90 min');
      expect(formatReadingTime(24000), '~1 h 36 min');
      expect(formatReadingTime(30000), '~2 h');
      expect(formatReadingTime(0), isNull);
    });

    test('a chapter row is words and minutes, never pages', () {
      expect(formatChapterLength(1240), '1,240 words · ~5 min');
      expect(formatChapterLength(1), '1 word · ~1 min');
      expect(formatChapterLength(0), isNull);
      expect(formatChapterLength(null), isNull);
    });

    test('a local word count matches the backend whitespace split', () {
      expect(countWords(['one two three', '  ', 'four\tfive\nsix']), 6);
      expect(countWords(const []), 0);
    });
  });
}
