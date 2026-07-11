import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/features/library/models/library_query.dart';

void main() {
  group('LibraryQuery', () {
    test('maps filter to reading status param', () {
      expect(
        const LibraryQuery(filter: LibraryFilter.reading).readingStatusParam,
        'reading',
      );
      expect(
        const LibraryQuery(filter: LibraryFilter.completed).readingStatusParam,
        'completed',
      );
      expect(
        const LibraryQuery(filter: LibraryFilter.downloaded).readingStatusParam,
        isNull,
      );
      expect(const LibraryQuery().readingStatusParam, isNull);
    });

    test('maps downloaded filter to has_chapters param', () {
      expect(
        const LibraryQuery(filter: LibraryFilter.downloaded).hasChaptersParam,
        isTrue,
      );
      expect(const LibraryQuery().hasChaptersParam, isNull);
      expect(
        const LibraryQuery(
          filter: LibraryFilter.downloaded,
          search: 'solo',
        ).hasChaptersParam,
        isTrue,
      );
    });

    test('uses listSeries fetch for search with downloaded filter', () {
      expect(
        const LibraryQuery(
          filter: LibraryFilter.downloaded,
          search: 'solo',
        ).usesListSeriesFetch,
        isTrue,
      );
      expect(
        const LibraryQuery(search: 'solo').usesListSeriesFetch,
        isFalse,
      );
    });

    test('maps sort to API param', () {
      expect(
        const LibraryQuery(sort: LibrarySort.dateAdded).sortParam,
        'date_added',
      );
      expect(
        const LibraryQuery().sortParam,
        'recent',
      );
      expect(
        const LibraryQuery(sort: LibrarySort.title).sortParam,
        'title',
      );
    });

    test('derives empty state from query', () {
      expect(
        const LibraryQuery(search: 'solo').emptyState,
        LibraryEmptyState.search,
      );
      expect(
        const LibraryQuery(filter: LibraryFilter.reading).emptyState,
        LibraryEmptyState.filter,
      );
      expect(const LibraryQuery().emptyState, LibraryEmptyState.library);
    });

    test('browse options expose required sort and filter labels', () {
      expect(
        libraryBrowseSortOptions.map((sort) => sort.label).toList(),
        ['Recently Read', 'Recently Added', 'Alphabetical'],
      );
      expect(
        libraryBrowseFilterOptions.map((filter) => filter.label).toList(),
        ['All', 'Downloaded', 'Reading', 'Completed'],
      );
    });
  });
}
