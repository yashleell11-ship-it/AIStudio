import 'package:aistudio_mobile/features/library/models/library_query.dart';
import 'package:flutter_test/flutter_test.dart';

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

    test('maps sort to API param', () {
      expect(
        const LibraryQuery(sort: LibrarySort.dateAdded).sortParam,
        'date_added',
      );
      expect(
        const LibraryQuery(sort: LibrarySort.recent).sortParam,
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
