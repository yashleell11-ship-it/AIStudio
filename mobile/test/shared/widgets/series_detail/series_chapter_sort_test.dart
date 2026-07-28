import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/shared/widgets/series_detail/series_chapter_sort.dart';

/// Minimal stand-in for the two very different chapter models the library and
/// source pages feed through the shared comparator.
typedef _Chapter = ({String id, double? number});

List<String> _idsOf(List<_Chapter> chapters) =>
    [for (final chapter in chapters) chapter.id];

List<String> _sorted(List<_Chapter> chapters, SeriesChapterSortOrder order) =>
    _idsOf(
      sortSeriesChapters(
        chapters,
        numberOf: (chapter) => chapter.number,
        order: order,
      ),
    );

void main() {
  group('sortSeriesChapters', () {
    const chapters = <_Chapter>[
      (id: 'b', number: 2),
      (id: 'a', number: 1),
      (id: 'c', number: 10),
    ];

    test('newest orders by descending chapter number', () {
      expect(_sorted(chapters, SeriesChapterSortOrder.newest), ['c', 'b', 'a']);
    });

    test('oldest orders by ascending chapter number', () {
      expect(_sorted(chapters, SeriesChapterSortOrder.oldest), ['a', 'b', 'c']);
    });

    test('compares numerically, not as text', () {
      // "10" sorts before "2" as a string; the top of a newest-first list is
      // the number this screen most has to get right.
      expect(_sorted(chapters, SeriesChapterSortOrder.newest).first, 'c');
    });

    test('orders decimal chapters between their neighbours', () {
      const withDecimal = <_Chapter>[
        (id: '12', number: 12),
        (id: '12.5', number: 12.5),
        (id: '13', number: 13),
      ];
      expect(
        _sorted(withDecimal, SeriesChapterSortOrder.oldest),
        ['12', '12.5', '13'],
      );
    });

    test('puts unnumbered chapters last in both directions', () {
      const withExtra = <_Chapter>[
        (id: 'extra', number: null),
        (id: 'one', number: 1),
        (id: 'two', number: 2),
      ];
      expect(
        _sorted(withExtra, SeriesChapterSortOrder.newest),
        ['two', 'one', 'extra'],
      );
      // Flipping the toggle must not promote an unnumbered extra to the top:
      // it is not the oldest chapter, it is a chapter of unknown position.
      expect(
        _sorted(withExtra, SeriesChapterSortOrder.oldest),
        ['one', 'two', 'extra'],
      );
    });

    test('keeps payload order when no chapter has a number', () {
      // A hand-imported folder: every comparison is a tie, and Dart's sort is
      // not stable, so without the index tie-break the list would come back
      // scrambled -- differently on every rebuild.
      const unnumbered = <_Chapter>[
        (id: 'first', number: null),
        (id: 'second', number: null),
        (id: 'third', number: null),
        (id: 'fourth', number: null),
        (id: 'fifth', number: null),
        (id: 'sixth', number: null),
        (id: 'seventh', number: null),
        (id: 'eighth', number: null),
        (id: 'ninth', number: null),
        (id: 'tenth', number: null),
        (id: 'eleventh', number: null),
        (id: 'twelfth', number: null),
      ];
      final expected = _idsOf(unnumbered);
      expect(_sorted(unnumbered, SeriesChapterSortOrder.newest), expected);
      expect(_sorted(unnumbered, SeriesChapterSortOrder.oldest), expected);
    });

    test('keeps payload order for chapters sharing a number', () {
      const duplicates = <_Chapter>[
        (id: 'part-a', number: 5),
        (id: 'part-b', number: 5),
        (id: 'part-c', number: 5),
      ];
      expect(
        _sorted(duplicates, SeriesChapterSortOrder.newest),
        ['part-a', 'part-b', 'part-c'],
      );
    });

    test('does not mutate the caller list', () {
      final input = [...chapters];
      sortSeriesChapters(
        input,
        numberOf: (chapter) => chapter.number,
        order: SeriesChapterSortOrder.oldest,
      );
      expect(_idsOf(input), ['b', 'a', 'c']);
    });

    test('handles an empty list', () {
      expect(_sorted(const [], SeriesChapterSortOrder.newest), isEmpty);
    });
  });
}
