import 'package:aistudio_mobile/features/library/models/library_query.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('LibraryQuery', () {
    test('maps filter to status param', () {
      expect(
        const LibraryQuery(filter: LibraryFilter.reading).statusParam,
        'reading',
      );
      expect(
        const LibraryQuery(filter: LibraryFilter.unread).statusParam,
        'unread',
      );
      expect(const LibraryQuery().statusParam, isNull);
    });

    test('maps sort to API param', () {
      expect(
        const LibraryQuery(sort: LibrarySort.dateAdded).sortParam,
        'date_added',
      );
      expect(
        const LibraryQuery(sort: LibrarySort.totalChapters).sortParam,
        'total_chapters',
      );
    });

    test('derives empty state from query', () {
      expect(
        const LibraryQuery(search: 'solo').emptyState,
        LibraryEmptyState.search,
      );
      expect(
        const LibraryQuery(favoritesOnly: true).emptyState,
        LibraryEmptyState.filter,
      );
      expect(const LibraryQuery().emptyState, LibraryEmptyState.library);
    });
  });
}
