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
      expect(const LibraryQuery().readingStatusParam, isNull);
    });

    test('maps sort to API param', () {
      expect(
        const LibraryQuery(sort: LibrarySort.recentlyAdded).sortParam,
        'recently_added',
      );
      expect(
        const LibraryQuery().sortParam,
        'recently_updated',
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
        ['Recently Updated', 'Recently Added', 'Alphabetical'],
      );
      expect(
        libraryBrowseFilterOptions.map((filter) => filter.label).toList(),
        ['All', 'Reading', 'Completed'],
      );
    });
  });
}
