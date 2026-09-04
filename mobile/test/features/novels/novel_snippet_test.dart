import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/features/novels/utils/novel_snippet.dart';

const _paragraphs = [
  'The first paragraph is short.',
  'Arthur set the book down and looked at the window for a long while, '
      'turning over what the old mage had said about mana cores and about '
      'the price of borrowing something that was never yours to begin with.',
  '',
];

void main() {
  group('novelSnippetAt', () {
    test('a bookmark at the start of a paragraph reads as the start of it',
        () {
      final (snippet, stale) = novelSnippetAt(_paragraphs, 1, 0);

      expect(snippet, 'The first paragraph is short.');
      expect(stale, isFalse);
      // No leading ellipsis: this really is where the paragraph begins.
      expect(snippet!.startsWith('…'), isFalse);
    });

    test('a bookmark partway in starts there, marked so it cannot be mistaken '
        'for the beginning', () {
      final (snippet, _) = novelSnippetAt(_paragraphs, 2, 0.5);

      expect(snippet, startsWith('…'));
      expect(snippet, isNot(contains('Arthur set the book down')));
      // Snapped back to a word boundary — never mid-word.
      expect(snippet!.substring(1).trimLeft(), isNot(startsWith(' ')));
      expect(_paragraphs[1], contains(snippet.substring(1).replaceAll('…', '')));
    });

    test('a long paragraph is capped and says it was cut', () {
      final long = List.filled(60, 'word').join(' ');
      final (snippet, _) = novelSnippetAt([long], 1, 0, maxChars: 40);

      expect(snippet!.length, lessThanOrEqualTo(41));
      expect(snippet, endsWith('…'));
    });

    test('a paragraph that no longer exists degrades to the nearest one and '
        'says so', () {
      final (snippet, stale) = novelSnippetAt(_paragraphs, 99, 0);

      expect(stale, isTrue);
      // The chapter's last paragraph is empty, so there is nothing to quote —
      // but it still resolved rather than failing.
      expect(snippet, '');
    });

    test('an index of 0 or below is read as the first paragraph', () {
      expect(novelSnippetAt(_paragraphs, 0, 0).$1, _paragraphs.first);
      expect(novelSnippetAt(_paragraphs, -5, 0).$1, _paragraphs.first);
    });

    test('a chapter with no text has no snippet, and is not called stale', () {
      final (snippet, stale) = novelSnippetAt(const [], 4, 0.5);
      expect(snippet, isNull);
      expect(stale, isFalse);
    });

    test('a fraction of 1.0 does not run off the end of the paragraph', () {
      final (snippet, _) = novelSnippetAt(_paragraphs, 1, 1);
      expect(snippet, isNotNull);
      expect(snippet, isNot(isEmpty));
    });

    test('a NaN or out-of-range fraction reads as the start', () {
      expect(
        novelSnippetAt(_paragraphs, 1, double.nan).$1,
        _paragraphs.first,
      );
      expect(novelSnippetAt(_paragraphs, 1, -3).$1, _paragraphs.first);
    });
  });
}
